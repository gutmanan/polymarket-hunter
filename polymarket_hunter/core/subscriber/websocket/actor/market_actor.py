import asyncio
import contextlib
from collections import deque
from typing import Deque, Optional

from polymarket_hunter.core.subscriber.websocket.actor.msg_envelope import MsgEnvelope
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageRouter
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class MarketActor:

    def __init__(
        self,
        market_id: str,
        router: MessageRouter,
        eval_interval_ms: int = 40,
        max_mailbox: int = 256,
    ) -> None:
        self.market_id = market_id
        self.router = router
        self.mailbox: Deque[MsgEnvelope] = deque(maxlen=max_mailbox)
        self._last_seq: Optional[int] = None
        self._tick_due = asyncio.Event()
        self._eval_interval = eval_interval_ms / 1000
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def post(self, env: MsgEnvelope) -> None:
        # Drop stale by seq if present
        if env.timestamp is not None and self._last_seq is not None and env.timestamp <= self._last_seq:
            return
        self.mailbox.append(env)
        self._tick_due.set()

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run(), name=f"actor-{self.market_id}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while self._running:
            await self._tick_due.wait()
            # micro-batch window to coalesce bursts
            await asyncio.sleep(self._eval_interval)
            self._tick_due.clear()

            if not self.mailbox:
                continue

            env = self.mailbox[-1]  # newest only
            if env.timestamp is not None:
                self._last_seq = env.timestamp

            try:
                await self.router.dispatch(env.payload)
            except Exception as e:
                logger.warning("Actor %s handler error: %s", self.market_id, e)
