import asyncio
from typing import Optional

from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.notifier.telegram_notifier import TelegramNotifier
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

class NotificationsSubscriber:
    def __init__(self):
        self._store = RedisNotificationStore(settings.REDIS_URL)
        self._telegram_notifier = TelegramNotifier()
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
                    print(payload)
                    if payload.medium == "telegram":
                        await self._telegram_notifier.send_message(payload)
                backoff = 0.5  # reset if stream ended cleanly
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("notifications subscribe error: %s; retrying in %.1fs", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
