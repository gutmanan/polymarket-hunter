import asyncio
import requests
import json
from websocket import WebSocketApp
import json
import time
import threading
from typing import Callable, Optional, Dict, Any
from src.utils.logger import setup_logger
from src.config.settings import settings

logger = setup_logger(__name__)

MARKET_CHANNEL = "market"
USER_CHANNEL = "user"

class PolymarketWebSocket:
    def __init__(self, channel_type, url, data, auth, message_callback, verbose):
        self.channel_type = channel_type
        self.url = url
        self.data = data
        self.auth = auth
        self.message_callback = message_callback
        self.verbose = verbose
        furl = url + "/ws/" + channel_type
        self.ws = WebSocketApp(
            furl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        self.orderbooks = {}

    def on_message(self, ws, message):
        print(message)
        pass

    def on_error(self, ws, error):
        print("Error: ", error)
        exit(1)

    def on_close(self, ws, close_status_code, close_msg):
        print("closing")
        exit(0)

    def on_open(self, ws):
        if self.channel_type == MARKET_CHANNEL:
            ws.send(json.dumps({"assets_ids": self.data, "type": MARKET_CHANNEL}))
        elif self.channel_type == USER_CHANNEL and self.auth:
            ws.send(
                json.dumps(
                    {"markets": self.data, "type": USER_CHANNEL, "auth": self.auth}
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


def get_markets_from_slug(slug: str) -> dict:
        API_BASE = "https://gamma-api.polymarket.com"
        print(f"Fetching market ID for slug: {slug}")
        url = f"{API_BASE}/events/slug/{slug}"
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data  # inspect it; it should contain condition_id, slug, outcomes, etc.

if __name__ == "__main__":
    url = "wss://ws-subscriptions-clob.polymarket.com"
    #Complete these by exporting them from your initialized client. 
    api_key = "9e6a0446-71ff-0e56-b26c-35b9ad65f701"
    api_secret = "kluI3do6m-eL3CtskrjQ1VouISC_mmfSuF_qleHX9lQ="
    api_passphrase = "f8847d0b9e08ff404aa20f0e05a066b791de68e28146549119c1e906e2ccdf30"
    slug = "trump-invokes-the-insurrection-act-in-2025"
    assets = [json.loads(market.get("clobTokenIds")) for market in get_markets_from_slug(slug).get("markets", [])]
    condition_ids = [] # no really need to filter by this one

    auth = {"apiKey": api_key, "secret": api_secret, "passphrase": api_passphrase}

    market_connection = PolymarketWebSocket(
        MARKET_CHANNEL, url, assets[0], auth, None, True
    )
    user_connection = PolymarketWebSocket(
        USER_CHANNEL, url, condition_ids, auth, None, True
    )

    market_connection.run()
    # user_connection.run()