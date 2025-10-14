import json
import threading
import time
from typing import Any

from websocket import WebSocketApp

from src.client.clob import CLOBClient
from src.client.data import DataClient
from src.client.gamma import GammaClient
from src.config.settings import settings
from src.utils.logger import setup_logger
from src.ws.handler.book_handler import BookHandler
from src.ws.handler.handlers import MessageContext, MessageRouter
from src.ws.handler.price_handler import PriceChangeHandler
from src.ws.handler.trade_handler import TradeHandler

logger = setup_logger(__name__)

MARKET_CHANNEL = "market"
USER_CHANNEL = "user"


class PolymarketWebSocket:
    def __init__(self, channel_type, slugs):
        self.channel_type = channel_type
        self.url = settings.POLYMARKET_WS_URL
        self.auth = settings.get_auth_creds()
        self.gamma_client = GammaClient()
        self.clob_client = CLOBClient()
        self.data_client = DataClient()

        self.markets = self.slugs_to_markets(slugs)
        self.assets_ids = [asset for market in self.markets for asset in json.loads(market["clobTokenIds"])]

        self.ws = WebSocketApp(
            f"{self.url}/ws/{self.channel_type}",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )

        # message handlers setup
        ctx = MessageContext(
            logger=logger,
            markets=self.markets,
            gamma_client=self.gamma_client,
            clob_client=self.clob_client,
            data_client=self.data_client
        )
        handlers = [
            PriceChangeHandler(),
            BookHandler(),
            TradeHandler()
        ]
        self.router = MessageRouter(handlers, ctx)

    def on_message(self, ws, message):
        if message == "PONG":  # server heartbeat
            return
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON message: {message[:200]}")
            return

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self.router.dispatch(item)
            return

        self.router.dispatch(payload)

    def on_error(self, ws, error):
        logger.warning(f"WS closed: error={error}")
        exit(1)

    def on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"WS closed: code={close_status_code} msg={close_msg}")
        exit(0)

    def on_open(self, ws):
        if self.channel_type == MARKET_CHANNEL:
            ws.send(json.dumps({"assets_ids": self.assets_ids, "type": MARKET_CHANNEL}))
        elif self.channel_type == USER_CHANNEL and self.auth:
            ws.send(
                json.dumps(
                    {
                        "markets": self.assets_ids,
                        "type": USER_CHANNEL,
                        "auth": self.auth,
                    }
                )
            )
        else:
            exit(1)

        thr = threading.Thread(target=self.ping, args=(ws,))
        thr.start()

    def ping(self, ws):
        while True:
            ws.send("PING")
            time.sleep(10)

    def run(self):
        self.ws.run_forever()

    def close(self):
        self.ws.close()

    def slugs_to_markets(self, slugs: list[str]) -> list[dict[str, Any]]:
        return [market for slug in slugs for market in self.gamma_client.get_markets_by_slug(slug)]
