import json
from typing import Iterable, List

import redis.asyncio as redis

SLUGS_KEY = "hunter:slugs"
EVENTS_CHANNEL = "hunter:slugs:events"


class RedisSlugStore:
    def __init__(self, redis_url: str):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    @property
    def client(self) -> redis.Redis:
        return self._redis

    # --- CRUD ---

    async def add(self, slug: str) -> None:
        added = await self._redis.sadd(SLUGS_KEY, slug)
        if added:
            await self._publish({"action": "add", "slug": slug})

    async def remove(self, slug: str) -> None:
        removed = await self._redis.srem(SLUGS_KEY, slug)
        if removed:
            await self._publish({"action": "remove", "slug": slug})

    async def list(self) -> List[str]:
        members = await self._redis.smembers(SLUGS_KEY)
        return sorted(members)

    async def replace_all(self, iterable: Iterable[str]) -> None:
        # replace the set transactionally
        slugs = set(iterable)
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.delete(SLUGS_KEY)
            if slugs:
                await pipe.sadd(SLUGS_KEY, *slugs)
            await pipe.execute()
        # publish replace events individually for simplicity
        for slug in slugs:
            await self._publish({"action": "add", "slug": slug})
        await self._publish({"action": "replace", "slug": None})

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
                    payload = json.loads(data)
                except Exception:
                    continue
                yield payload
        finally:
            await pubsub.unsubscribe(EVENTS_CHANNEL)
            await pubsub.close()
