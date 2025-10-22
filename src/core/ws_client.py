# src/core/ws_client.py
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, List

import websockets
from websockets.legacy.client import WebSocketClientProtocol

from src.config.settings import settings
from src.core.client.clob import CLOBClient
from src.core.client.data import DataClient
from src.core.client.gamma import GammaClient
from src.core.handler.handlers import MessageRouter, MessageContext  # async router
from src.core.handler.price_handler import PriceChangeHandler
from src.core.handler.book_handler import BookHandler
from src.core.handler.trade_handler import TradeHandler
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MarketWSClient:
    """
    Fully async WS client with auto-reconnect and dynamic resubscribe on slug updates.
    - Uses websockets (async)
    - Pings every 10s with "PING"
    - Reconnects with capped backoff
    - Calls an *async* MessageRouter
    """

    def __init__(self, slugs: List[str]):
        self._gamma = GammaClient()
        self._clob = CLOBClient()
        self._data = DataClient()

        self._slugs: List[str] = slugs[:]
        self._markets = self._slugs_to_markets_sync(self._slugs)  # initial (sync)
        self._assets_ids = [a for m in self._markets for a in json.loads(m["clobTokenIds"])]

        ctx = MessageContext(
            logger=logger,
            markets=self._markets,
            gamma_client=self._gamma,
            clob_client=self._clob,
            data_client=self._data,
        )
        handlers = [PriceChangeHandler(), BookHandler(), TradeHandler()]
        self._router = MessageRouter(handlers, ctx, concurrent=True)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._restart = asyncio.Event()
        self._ws: WebSocketClientProtocol | None = None

    # ----- public API -----

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._close_ws()

    async def update_slugs(self, slugs: List[str]) -> None:
        # dedupe & keep order
        uniq = list(dict.fromkeys(slugs))
        if uniq == self._slugs:
            return
        self._slugs = uniq
        # refresh markets/assets (Gamma client is sync → offload)
        self._markets = await asyncio.to_thread(self._slugs_to_markets_sync, self._slugs)
        self._assets_ids = [a for m in self._markets for a in json.loads(m["clobTokenIds"])]
        self._router.ctx.update_markets(self._markets)
        # trigger resubscribe
        self._restart.set()
        await self._close_ws()

    # ----- internals -----

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self._restart.clear()
            try:
                await self._connect_and_pump()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"WS client error: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect_and_pump(self) -> None:
        async with websockets.connect(settings.POLYMARKET_WS_URL, ping_interval=None) as ws:
            self._ws = ws
            await self._send_subscribe(ws)
            ping_task = asyncio.create_task(self._ping(ws))
            try:
                while not (self._stop.is_set() or self._restart.is_set()):
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        # recv timeout is okay; ping task keeps link alive
                        continue
                    if message == "PONG":
                        continue
                    await self._handle_message(message)
            finally:
                ping_task.cancel()
                with contextlib.suppress(Exception):
                    await ping_task
        self._ws = None

    async def _send_subscribe(self, ws: WebSocketClientProtocol) -> None:
        payload = {"assets_ids": self._assets_ids, "type": "markets"}
        try:
            await ws.send(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to send subscribe: {e}")

    async def _ping(self, ws: WebSocketClientProtocol) -> None:
        while True:
            await asyncio.sleep(10)
            try:
                await ws.send("PING")
            except Exception:
                return

    async def _handle_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON message: {message[:180]}")
            return

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    await self._router.dispatch(item)
            return
        if isinstance(payload, dict):
            await self._router.dispatch(payload)

    async def _close_ws(self) -> None:
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._ws = None

    # Gamma get_markets_by_slug is sync; keep a tiny sync helper and call via to_thread
    def _slugs_to_markets_sync(self, slugs: List[str]) -> List[dict[str, Any]]:
        return [m for slug in slugs for m in self._gamma.get_markets_by_slug(slug)]
