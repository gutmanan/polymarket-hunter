from __future__ import annotations

import asyncio
import contextlib
import json
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
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class UserWSClient:

    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._market_ids = []

        self.markets = []
        self.ctx = MessageContext(
            logger=logger,
            markets=self.markets
        )

        self._actors = ActorManager(self.ctx, ActorType.USER)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._restart = asyncio.Event()
        self._ws: WebSocketClientProtocol | None = None

        self._update_lock = asyncio.Lock()

    # ---------- Public API ----------

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="user-wsclient-runner")

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
            self._market_ids = [m["conditionId"] for m in self.markets]
            self.ctx.update_markets(self.markets)
            self._restart.set()
            if self._ws:
                with contextlib.suppress(Exception):
                    await self._ws.close(code=4000, reason="resubscribe")

    # ----- internals -----

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_and_pump()
                self._restart.clear()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("WS client error: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def _connect_and_pump(self) -> None:
        async with websockets.connect(
            settings.POLYMARKET_WS_URL + "/user",
            ping_interval=20,
            ping_timeout=30,
            max_queue=1000,     # guard on incoming frames
        ) as ws:
            self._ws = ws
            await self._send_subscribe(ws)

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
        api_key = self._clob.client.derive_api_key()
        auth = {"apikey": api_key.api_key, "secret": api_key.api_secret, "passphrase": api_key.api_passphrase}
        payload = {"auth": auth, "markets": self._market_ids, "type": "user"}
        try:
            await ws.send(json.dumps(payload))
            logger.info("WS subscribe sent: %d markets", len(self.markets))
        except Exception as e:
            logger.warning("Failed to send subscribe: %s", e)

    # -------- ingestion → actors --------

    def _ingest_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Non-JSON message: %s", raw[:180])
            return

        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self._route_to_actor(item)
            return

        if isinstance(payload, dict):
            self._route_to_actor(payload)

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
        for slug in slugs:
            try:
                m = await self._gamma.get_market_by_slug(slug)
                if m:
                    markets.append(m)
            except Exception as e:
                logger.warning("Failed to resolve slug %s: %s", slug, e)
        return markets