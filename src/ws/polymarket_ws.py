import json
import threading
import time

from websocket import WebSocketApp

from src.client.gamma_client import GammaClient
from src.config.settings import settings
from src.utils.logger import setup_logger
from src.ws.book_handler import BookHandler
from src.ws.handlers import MessageContext, MessageRouter
from src.ws.price_handler import PriceChangeHandler

logger = setup_logger(__name__)

MARKET_CHANNEL = "market"
USER_CHANNEL = "user"

class PolymarketWebSocket:
    def __init__(self, channel_type, market_assets):
        self.channel_type = channel_type
        self.url = settings.POLYMARKET_WS_URL
        self.auth = settings.get_auth_creds()
        self.data = market_assets
        self.ws = WebSocketApp(
            f"{self.url}/ws/{self.channel_type}",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        # message handlers setup
        ctx = MessageContext(logger=logger, gamma_client=GammaClient())
        handlers = [
            PriceChangeHandler(),
            BookHandler()
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
        print("closing")
        exit(0)

    def on_open(self, ws):
        if self.channel_type == MARKET_CHANNEL:
            ws.send(json.dumps({"assets_ids": self.data, "type": MARKET_CHANNEL}))
        elif self.channel_type == USER_CHANNEL and self.auth:
            ws.send(json.dumps({"markets": self.data, "type": USER_CHANNEL, "auth": self.auth}))
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

if __name__ == "__main__":
    slug = "bitcoin-up-or-down-october-11-4am-et"
    gamma = GammaClient()
    assets = [json.loads(market.get("clobTokenIds")) for market in gamma.get_markets_by_slug(slug)]
    market_connection = PolymarketWebSocket(MARKET_CHANNEL, assets[0])
    market_connection.run()
