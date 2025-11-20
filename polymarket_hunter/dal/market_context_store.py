from __future__ import annotations

import json

import redis.asyncio as redis

from polymarket_hunter.dal import REDIS_CLIENT
from polymarket_hunter.dal.datamodel.market_context import MarketContext

EVENTS_CHANNEL = "hunter:market_context:events"


class RedisMarketContextStore:
    def __init__(self):
        self._redis = REDIS_CLIENT

    @property
    def client(self) -> redis.Redis:
        return self._redis

    # ---------- CRUD ----------

    async def publish(self, context: MarketContext) -> None:
        raw = context.model_dump_json()
        await self._publish({"action": "add", "context": raw})

    # ---------- Pub/Sub ----------

    async def _publish(self, message: dict) -> None:
        await self._redis.publish(EVENTS_CHANNEL, json.dumps(message))

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
                    yield json.loads(data)
                except Exception:
                    continue
        finally:
            await pubsub.unsubscribe(EVENTS_CHANNEL)
            await pubsub.close()
