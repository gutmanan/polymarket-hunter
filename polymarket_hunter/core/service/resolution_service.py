import asyncio
import time
import uuid
from functools import lru_cache
from typing import List, Any, Dict, Tuple

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.service.trade_service import TradeService
from polymarket_hunter.dal.datamodel.strategy_action import Side
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.helper import market_has_ended, ts_to_seconds
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

STALE_ORDER_SECONDS = 300

class ResolutionService:
    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._order_store = RedisOrderRequestStore()
        self._trade_store = RedisTradeRecordStore()
        self._trade_service = TradeService()

    # ---------- utilities ----------

    def _market_cache(self) -> Dict[str, Any]:
        return {}

    async def _get_market_cached(self, market_id: str, cache: Dict[str, Any]) -> Any:
        if market_id not in cache:
            cache[market_id] = await self._clob.get_market_async(market_id)
        return cache[market_id]

    async def _build_trade_record(self, pos: Dict[str, Any]) -> TradeRecord:
        market_id = pos["conditionId"]
        asset_id = pos["asset"]
        side = Side.SELL
        order_id = uuid.uuid4().hex
        status = "REDEEMED"
        size_orig = pos["size"]
        size_mat = pos["currentValue"]
        price = size_orig / size_mat if size_mat > 0 else 0
        req = await self._order_store.get(market_id, asset_id, Side.BUY)

        return TradeRecord(
            market_id=market_id,
            asset_id=asset_id,
            side=side,
            order_id=order_id,
            slug=pos["slug"],
            outcome=pos["outcome"],
            matched_amount=size_mat,
            size=size_orig,
            price=price,
            trader_side="TAKER",
            status=status,
            active=True,
            order_request=req,
            raw_events=[dict(pos)],
            event_type="resolution",
            matched_ts=time.time()
        )

    async def _deactivate_opposite(self, tr):
        opposite_side = Side.BUY if tr.side == Side.SELL else Side.SELL
        existing_opposite = await self._trade_store.get_active(tr.market_id, tr.asset_id, opposite_side)
        if existing_opposite:
            deactivate = existing_opposite.model_copy(update={"active": False})
            deactivate.touch()
            await self._trade_store.update(deactivate)
            await self._order_store.remove(tr.market_id, tr.asset_id, opposite_side)

    # ---------- public APIs ----------

    async def cancel_stale_orders(self) -> Dict[str, List[Tuple[str, Any, dict]]]:
        """
        Returns: {
          "ok":    [(order_id, response), ...],
          "fail":  [(order_id, Exception or error_msg), ...],
        }
        """
        markets: Dict[str, Any] = self._market_cache()
        results_ok: List[Tuple[str, Any, dict]] = []
        results_fail: List[Tuple[str, Any, dict]] = []

        try:
            orders = await self._clob.get_orders_async()
        except Exception as e:
            return {"ok": [], "fail": [("get_orders", e)]}

        for o in orders:
            if str(o.get("status")).upper() != "LIVE":
                continue
            try:
                m = await self._get_market_cached(o["market"], markets)
                is_resolved = await self._data.is_market_resolved(o["market"])
                if not market_has_ended(m) or not is_resolved:
                    continue

                now = time.time()
                created_at = ts_to_seconds(o["created_at"])

                age = now - created_at
                if age < STALE_ORDER_SECONDS:
                    continue

                try:
                    res = await self._clob.cancel_order_async(o["id"])
                    results_ok.append((o["id"], res, o))
                except Exception as e:
                    results_fail.append((o["id"], e, o))
            except Exception as e:
                results_fail.append((o.get("id", "?"), e, o))

        return {"ok": results_ok, "fail": results_fail}

    async def redeem_resolved_positions(self) -> Dict[str, List[Tuple[str, Any, dict]]]:
        """
        Returns: {
          "ok":    [(condition_id, response), ...],
          "fail":  [(condition_id, Exception or error_msg), ...],
        }
        """
        markets: Dict[str, Any] = self._market_cache()
        results_ok: List[Tuple[str, Any, dict]] = []
        results_fail: List[Tuple[str, Any, dict]] = []

        try:
            positions = await self._data.get_positions()
        except Exception as e:
            return {"ok": [], "fail": [("get_positions", e)]}

        for p in positions:
            cid = p.get("conditionId")
            if not cid:
                continue
            try:
                m = await self._get_market_cached(cid, markets)
                is_resolved = await self._data.is_market_resolved(cid)
                if not market_has_ended(m) or not is_resolved:
                    continue

                try:
                    res = await self._data.redeem_position(cid)
                    tr = await self._build_trade_record(p)
                    await self._deactivate_opposite(tr)
                    await self._trade_store.add(tr)
                    results_ok.append((cid, res, p))
                except Exception as e:
                    results_fail.append((cid, e, p))
            except Exception as e:
                results_fail.append((cid or "?", e, p))

        return {"ok": results_ok, "fail": results_fail}

@lru_cache(maxsize=1)
def get_resolution_service() -> ResolutionService:
    return ResolutionService()


if __name__ == "__main__":
    keeper = ResolutionService()
    res = asyncio.run(keeper.redeem_resolved_positions())
    print(res)