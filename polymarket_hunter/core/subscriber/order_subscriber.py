import asyncio
from typing import Optional

from polymarket_hunter.core.service.order_service import OrderService
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

class OrdersSubscriber:
    def __init__(self):
        self._store = RedisOrderRequestStore()
        self._service = OrderService()
        self._task: Optional[asyncio.Task] = None

    async def start(self):
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass

    async def _run(self):
        backoff = 0.5
        while True:
            try:
                async for payload in self._store.subscribe_events():
                    await self._service.execute_order(payload)
                backoff = 0.5  # reset if stream ended cleanly
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("orders subscribe error: %s; retrying in %.1fs", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
