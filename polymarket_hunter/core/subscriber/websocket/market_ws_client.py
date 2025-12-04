# polymarket_hunter/core/ws_client.py
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any, List

import websockets
from websockets.legacy.client import WebSocketClientProtocol

from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.subscriber.websocket.actor.actor_manager import ActorManager, ActorType
from polymarket_hunter.core.subscriber.websocket.actor.msg_envelope import MsgEnvelope
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageContext
from polymarket_hunter.core.subscriber.websocket.observability_ws_client import CLIENT_UPTIME_SECONDS, MESSAGE_COUNT, \
    SLUG_RESOLUTION_LATENCY, WS_SETUP_LATENCY
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class MarketWSClient:

    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._assets_ids = []

        self.markets = []
        self.ctx = MessageContext(
            logger=logger,
            markets=self.markets
        )

        self._actors = ActorManager(self.ctx, ActorType.MARKET)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._restart = asyncio.Event()
        self._ws: WebSocketClientProtocol | None = None

        self._update_lock = asyncio.Lock()
        CLIENT_UPTIME_SECONDS.set_to_current_time()

    # ---------- Public API ----------

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="market-wsclient-runner")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._close_ws()
        await self._actors.stop_all()

    async def update_slugs(self, slugs: List[str]) -> None:
        """
        Update the tracked slugs -> resolve to markets -> trigger resubscribe.
        """
        async with self._update_lock:
            self.markets = await self._slugs_to_markets(slugs)
            if not self.markets:
                return
            self._assets_ids = [a for m in self.markets for a in json.loads(m.get("clobTokenIds") or [])]
            self.ctx.update_markets(self.markets)
            self._restart.set()
            if self._ws:
                with contextlib.suppress(Exception):
                    await self._ws.close(code=4000, reason="resubscribe")

    # ----- internals -----

    async def _run(self) -> None:
        backoff = 1.0
        CLIENT_UPTIME_SECONDS.set_to_current_time()
        while not self._stop.is_set():
            try:
                await self._connect_and_pump()
                self._restart.clear()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                CLIENT_UPTIME_SECONDS.set(0)
                logger.warning("WS client error: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def _connect_and_pump(self) -> None:
        start_time = time.monotonic()
        async with websockets.connect(
            settings.POLYMARKET_WS_URL + "/market",
            ping_interval=20,
            ping_timeout=30,
            max_queue=1000,     # guard on incoming frames
        ) as ws:
            self._ws = ws
            await self._send_subscribe(ws)

            setup_duration = time.monotonic() - start_time
            WS_SETUP_LATENCY.observe(setup_duration)

            logger.info("WS setup complete in %.3f seconds", setup_duration)
            while True:
                recv_task = asyncio.create_task(ws.recv(), name="ws-recv")
                stop_task = asyncio.create_task(self._stop.wait(), name="ws-stop")
                restart_task = asyncio.create_task(self._restart.wait(), name="ws-restart")

                done, pending = await asyncio.wait(
                    {recv_task, stop_task, restart_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()

                if stop_task in done and self._stop.is_set():
                    break
                if restart_task in done and self._restart.is_set():
                    break

                if recv_task in done:
                    message = recv_task.result()
                    if message == "PONG":
                        continue
                    # Fast, non-blocking: parse + enqueue to actors
                    self._ingest_message(message)

        self._ws = None

    async def _send_subscribe(self, ws: WebSocketClientProtocol) -> None:
        payload = {"assets_ids": self._assets_ids, "type": "markets"}
        try:
            await ws.send(json.dumps(payload))
            logger.info("WS subscribe sent: %d markets -> %d assets", len(self.markets), len(self._assets_ids))
        except Exception as e:
            logger.warning("Failed to send subscribe: %s", e)

    # -------- ingestion → actors --------

    def _ingest_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            MESSAGE_COUNT.labels('json_error').inc()
            logger.debug("Non-JSON message: %s", raw[:180])
            return

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self._route_to_actor(item)
                    MESSAGE_COUNT.labels(item.get("event_type", "unknown")).inc()
            return

        if isinstance(payload, dict):
            self._route_to_actor(payload)
            MESSAGE_COUNT.labels(payload.get("event_type", "unknown")).inc()

    def _route_to_actor(self, item: dict) -> None:
        market, timestamp, event_type = item.get("market"), item.get("timestamp"), item.get("event_type")
        env = MsgEnvelope(market=market, timestamp=timestamp, event_type=event_type, payload=item)
        self._actors.get(market).post(env)

    async def _close_ws(self) -> None:
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._ws = None

    async def _slugs_to_markets(self, slugs: List[str]) -> List[dict[str, Any]]:
        markets: List[dict[str, Any]] = []
        with SLUG_RESOLUTION_LATENCY.time():
            for slug in slugs:
                try:
                    m = await self._gamma.get_market_by_slug(slug)
                    if m:
                        markets.append(m)
                except Exception as e:
                    logger.warning("Failed to resolve slug %s: %s", slug, e)
        return markets