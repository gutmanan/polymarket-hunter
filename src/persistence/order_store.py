from __future__ import annotations

import json
import time
from dataclasses import asdict, replace
from typing import Iterable, Optional

import redis.asyncio as redis

from src.persistence.datamodel.order import Order


ORDERS_KEYSET = "hunter:orders"
ORDER_KEY_TPL = "hunter:order:{market_id}:{asset_id}"


class RedisOrderStore:
    def __init__(self, redis_url: str):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    def _key(self, market_id: str, asset_id: str) -> str:
        return ORDER_KEY_TPL.format(market_id=market_id, asset_id=asset_id)

    # --- CRUD ---

    async def add(self, order: Order) -> None:
        raw = json.dumps(asdict(order), ensure_ascii=False)
        key = self._key(order.market_id, order.asset_id)
        await self._redis.set(key, raw)
        await self._redis.sadd(ORDERS_KEYSET, key)

    async def get(self, market_id: str, asset_id: str) -> Optional[Order]:
        raw = await self._redis.get(self._key(market_id, asset_id))
        if not raw:
            return None
        return Order(**json.loads(raw))

    async def update(self, market_id: str, asset_id: str, **fields) -> Optional[Order]:
        current = await self.get(market_id, asset_id)
        if not current:
            return None
        fields.setdefault("updated_ts", time.time())
        new = replace(current, **fields)
        await self._redis.set(self._key(market_id, asset_id), json.dumps(asdict(new), ensure_ascii=False))
        return new

    async def remove(self, market_id: str, asset_id: str) -> None:
        key = self._key(market_id, asset_id)
        await self._redis.delete(key)
        await self._redis.srem(ORDERS_KEYSET, key)

    # --- Lists ---

    async def list_keys(self) -> list[str]:
        keys = await self._redis.smembers(ORDERS_KEYSET)
        return sorted(keys)

    async def list_all(self, limit: Optional[int] = None) -> list[Order]:
        keys = await self.list_keys()
        if limit:
            keys = keys[:limit]
        if not keys:
            return []
        pipe = self._redis.pipeline()
        for k in keys:
            pipe.get(k)
        raws = await pipe.execute()
        return [Order(**json.loads(r)) for r in raws if r]

    # --- Utilities ---

    async def upsert(self, order: Order) -> None:
        raw = json.dumps(asdict(order), ensure_ascii=False)
        key = self._key(order.market_id, order.asset_id)
        await self._redis.set(key, raw)
        await self._redis.sadd(ORDERS_KEYSET, key)
