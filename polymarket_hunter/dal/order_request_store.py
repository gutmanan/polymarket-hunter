from __future__ import annotations

import json
from typing import Optional, List

import redis.asyncio as redis

from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.db import REDIS_CLIENT

ORDERS_KEY = "hunter:order_requests"
DOC_PREFIX = "hunter:order_requests:doc:"
EVENTS_CHANNEL = "hunter:order_requests:events"


class RedisOrderRequestStore:
    def __init__(self):
        self._redis = REDIS_CLIENT

    @property
    def client(self) -> redis.Redis:
        return self._redis

    # ---------- keys ----------
    @staticmethod
    def _set_key(market_id: str, asset_id: str, side: str) -> str:
        return f"{market_id}:{asset_id}:{side}"

    @staticmethod
    def _doc_key(market_id: str, asset_id: str, side: str) -> str:
        return f"{DOC_PREFIX}{market_id}:{asset_id}:{side}"

    # ---------- CRUD ----------

    async def contains(self, market_id: str, asset_id: str, side: str) -> bool:
        return await self._redis.sismember(ORDERS_KEY, self._set_key(market_id, asset_id, side))

    async def add(self, order: OrderRequest) -> None:
        """
        Upsert behavior:
        - ensure key present in the set
        - store full JSON doc at DOC_PREFIX...
        - publish 'add' if new, 'update' if existing
        """
        skey = self._set_key(order.market_id, order.asset_id, order.side)
        dkey = self._doc_key(order.market_id, order.asset_id, order.side)
        raw = order.model_dump_json()

        pipe = self._redis.pipeline(transaction=True)
        pipe.sadd(ORDERS_KEY, skey)
        pipe.set(dkey, raw)
        sadd_res, _ = await pipe.execute()

        event = "add" if sadd_res == 1 else "update"
        await self._publish({"action": event, "key": skey, "order": raw})

    async def get(self, market_id: str, asset_id: str, side: str) -> Optional[OrderRequest]:
        dkey = self._doc_key(market_id, asset_id, side)
        raw = await self._redis.get(dkey)
        if not raw:
            return None
        return OrderRequest.model_validate_json(raw)

    async def update(self, order: OrderRequest) -> None:
        """Simple upsert without re-publishing add/update differentiation"""
        skey = self._set_key(order.market_id, order.asset_id, order.side)
        dkey = self._doc_key(order.market_id, order.asset_id, order.side)
        order.touch()
        raw = order.model_dump_json()

        await self._redis.set(dkey, raw)
        await self._publish({"action": "update", "key": skey, "order": raw})

    async def remove(self, market_id: str, asset_id: str, side: str) -> None:
        skey = self._set_key(market_id, asset_id, side)
        dkey = self._doc_key(market_id, asset_id, side)
        pipe = self._redis.pipeline(transaction=True)
        pipe.srem(ORDERS_KEY, skey)
        pipe.delete(dkey)
        removed, _ = await pipe.execute()
        if removed:
            await self._publish({"action": "remove", "key": skey})

    async def list_keys(self) -> List[str]:
        members = await self._redis.smembers(ORDERS_KEY)
        return sorted(members)

    async def list_docs(self) -> List[OrderRequest]:
        """
        Fetch all stored OrderRequests.
        """
        keys = await self.list_keys()
        if not keys:
            return []
        doc_keys = [f"{DOC_PREFIX}{k}" for k in keys]
        raws = await self._redis.mget(doc_keys)
        out: List[OrderRequest] = []
        for raw in raws:
            if not raw:
                continue
            try:
                out.append(OrderRequest.model_validate_json(raw))
            except Exception:
                # skip malformed entry
                continue
        return out

    async def cleanup_stale_pointers(self) -> int:
        skeys = await self._redis.smembers(ORDERS_KEY)
        if not skeys:
            return 0

        stale_keys_to_remove: List[str] = []
        check_pipe = self._redis.pipeline(transaction=False)
        dkeys_map = {}

        for skey in skeys:
            parts = skey.split(':')
            if len(parts) != 3:
                stale_keys_to_remove.append(skey)
                continue

            market_id, asset_id, side = parts
            dkey = self._doc_key(market_id, asset_id, side)
            check_pipe.exists(dkey)
            dkeys_map[dkey] = skey

        exists_results = await check_pipe.execute()

        for dkey, exists_result in zip(dkeys_map.keys(), exists_results):
            skey = dkeys_map[dkey]
            if exists_result == 0:
                stale_keys_to_remove.append(skey)

        removed_count = 0
        if stale_keys_to_remove:
            remove_pipe = self._redis.pipeline(transaction=True)
            remove_pipe.srem(ORDERS_KEY, *stale_keys_to_remove)

            results = await remove_pipe.execute()
            removed_count = results[0]

        return removed_count

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
