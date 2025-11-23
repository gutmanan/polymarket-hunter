from __future__ import annotations

import json
from typing import Optional, List, AsyncIterator

import redis.asyncio as redis

from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.db import REDIS_CLIENT

TRADE_RECORDS_KEY = "hunter:trade_records"
DOC_PREFIX = "hunter:trade_records:doc:"
EVENTS_CHANNEL = "hunter:trade_records:events"


class RedisTradeRecordStore:
    def __init__(self):
        self._redis = REDIS_CLIENT

    @property
    def client(self) -> redis.Redis:
        return self._redis

    # ---------- key builders ----------
    @staticmethod
    def _set_key(market_id: str, asset_id: str, side: str, order_id: str) -> str:
        return f"{market_id}:{asset_id}:{side}:{order_id}"

    @staticmethod
    def _doc_key(market_id: str, asset_id: str, side: str, order_id: str) -> str:
        return f"{DOC_PREFIX}{market_id}:{asset_id}:{side}:{order_id}"

    def _build_pattern(self, market_id: Optional[str], asset_id: Optional[str], side: Optional[str]) -> str:
        parts = [market_id or "*", asset_id or "*", side or "*", "*"]
        return ":".join(parts)

    def _record_ts(self, rec: "TradeRecord") -> float:
        try:
            return float(rec.created_ts or 0)
        except Exception:
            return 0

    async def _iter_records(self, pattern: str, *, page_size: int = 1000) -> AsyncIterator["TradeRecord"]:
        cursor: int | str = 0
        while True:
            cursor, members = await self._redis.sscan(TRADE_RECORDS_KEY, cursor=cursor, match=pattern, count=page_size)
            if members:
                doc_keys = [f"{DOC_PREFIX}{m}" for m in members]
                raws = await self._redis.mget(doc_keys)
                for raw in raws:
                    if not raw:
                        continue
                    try:
                        yield TradeRecord.model_validate_json(raw)
                    except Exception:
                        # skip malformed docs
                        continue
            if cursor in (0, "0"):
                break

    # ---------- CRUD ----------

    async def contains(self, market_id: str, asset_id: str, side: str, order_id) -> bool:
        return await self._redis.sismember(TRADE_RECORDS_KEY, self._set_key(market_id, asset_id, side, order_id))

    async def add(self, req: OrderRequest, rec: TradeRecord) -> None:
        """
        Upsert behavior:
        - ensure the key exists in hunter:trade_records set
        - store full TradeRecord JSON doc at DOC_PREFIX...
        - publish 'add' if new, 'update' if already existed
        """
        skey = self._set_key(rec.market_id, rec.asset_id, rec.side, rec.order_id)
        dkey = self._doc_key(rec.market_id, rec.asset_id, rec.side, rec.order_id)
        raw_order = req.model_dump_json()
        raw_trade = rec.model_dump_json()

        pipe = self._redis.pipeline(transaction=True)
        pipe.sadd(TRADE_RECORDS_KEY, skey)
        pipe.set(dkey, raw_trade)
        sadd_res, _ = await pipe.execute()

        event = "add" if sadd_res == 1 else "update"
        await self._publish({"action": event, "key": skey, "order_request": raw_order, "trade_record": raw_trade})

    async def get(self, market_id: str, asset_id: str, side: str, order_id: str) -> Optional[TradeRecord]:
        raw = await self._redis.get(self._doc_key(market_id, asset_id, side, order_id))
        if not raw:
            return None
        return TradeRecord.model_validate_json(raw)

    async def get_active(self, market_id: str, asset_id: Optional[str] = None, side: Optional[str] = None) -> Optional["TradeRecord"]:
        pattern = self._build_pattern(market_id, asset_id, side)
        best: Optional[TradeRecord] = None

        async for rec in self._iter_records(pattern):
            if rec.active:
                best = rec

        return best

    async def get_all(self, market_id: str, asset_id: Optional[str] = None, side: Optional[str] = None, *, sort_desc: bool = True) -> List["TradeRecord"]:
        pattern = self._build_pattern(market_id, asset_id, side)
        items = [rec async for rec in self._iter_records(pattern)]
        items.sort(key=lambda rec: rec.created_ts, reverse=sort_desc)
        return items

    async def update(self, rec: TradeRecord) -> None:
        """Simple upsert without re-publishing add/update differentiation"""
        skey = self._set_key(rec.market_id, rec.asset_id, rec.side, rec.order_id)
        dkey = self._doc_key(rec.market_id, rec.asset_id, rec.side, rec.order_id)
        rec.touch()
        raw = rec.model_dump_json()

        await self._redis.set(dkey, raw)
        await self._publish({"action": "update", "key": skey, "trade_record": raw})

    async def remove(self, market_id: str, asset_id: str, side: str, order_id: str) -> None:
        skey = self._set_key(market_id, asset_id, side, order_id)
        dkey = self._doc_key(market_id, asset_id, side, order_id)
        pipe = self._redis.pipeline(transaction=True)
        pipe.srem(TRADE_RECORDS_KEY, skey)
        pipe.delete(dkey)
        removed, _ = await pipe.execute()
        if removed:
            await self._publish({"action": "remove", "key": skey})

    async def list_keys(self) -> List[str]:
        members = await self._redis.smembers(TRADE_RECORDS_KEY)
        return sorted(members)

    async def list_docs(self) -> List[TradeRecord]:
        """Fetch all stored TradeRecords"""
        keys = await self.list_keys()
        if not keys:
            return []
        doc_keys = [f"{DOC_PREFIX}{k}" for k in keys]
        raws = await self._redis.mget(doc_keys)
        out: List[TradeRecord] = []
        for raw in raws:
            if not raw:
                continue
            try:
                out.append(TradeRecord.model_validate_json(raw))
            except Exception:
                continue
        return out

    # ---------- Pub/Sub ----------

    async def _publish(self, message: dict) -> None:
        await self._redis.publish(EVENTS_CHANNEL, json.dumps(message))

    async def subscribe_events(self):
        """Async generator yielding every pub/sub event as dict"""
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
