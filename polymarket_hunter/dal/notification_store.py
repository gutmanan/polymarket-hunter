from __future__ import annotations

import redis.asyncio as redis

from polymarket_hunter.dal import REDIS_CLIENT
from polymarket_hunter.dal.datamodel.notification import Notification

EVENTS_CHANNEL = "hunter:notifications:events"


class RedisNotificationStore:
    def __init__(self):
        self._redis = REDIS_CLIENT

    @property
    def client(self) -> redis.Redis:
        return self._redis

    # ---------- CRUD ----------

    async def send_message(self, text: str):
        notification = Notification(text=text)
        await self._publish(notification)

    # ---------- Pub/Sub ----------

    async def _publish(self, notification: Notification) -> None:
        await self._redis.publish(EVENTS_CHANNEL, notification.model_dump_json())

    async def subscribe_events(self):
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(EVENTS_CHANNEL)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode()
                try:
                    yield Notification.model_validate_json(data)
                except Exception:
                    continue
        finally:
            await pubsub.unsubscribe(EVENTS_CHANNEL)
            await pubsub.close()
