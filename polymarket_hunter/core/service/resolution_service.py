import asyncio
import time
from functools import lru_cache
from typing import List, Any, Dict, Tuple

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.service.trade_service import TradeService
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import market_has_ended, to_seconds

logger = setup_logger(__name__)

STALE_ORDER_SECONDS = 300

class ResolutionService:
    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._trade_store = RedisTradeRecordStore()
        self._trade_service = TradeService()

    # ---------- utilities ----------

    def _market_cache(self) -> Dict[str, Any]:
        return {}

    async def _get_market_cached(self, market_id: str, cache: Dict[str, Any]) -> Any:
        if market_id not in cache:
            cache[market_id] = await self._clob.get_market_async(market_id)
        return cache[market_id]

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
                created_at = to_seconds(o["created_at"])

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
                    res = await self._data.redeem_position_async(cid)
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