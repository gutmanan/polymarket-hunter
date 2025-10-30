import asyncio
from functools import lru_cache
from typing import List, Any, Dict, Tuple

from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.strategy.strategy_evaluator import StrategyEvaluator
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import market_has_ended, retryable, _with_timeout

logger = setup_logger(__name__)


class ResolutionService:
    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._store = RedisOrderRequestStore(settings.REDIS_URL)
        self._evaluator = StrategyEvaluator()

    # ---------- utilities ----------

    def _market_cache(self) -> Dict[str, Any]:
        return {}

    async def _get_market_cached(self, market_id: str, cache: Dict[str, Any]) -> Any:
        if market_id not in cache:
            cache[market_id] = await self._clob.get_market_retry(market_id)
        return cache[market_id]

    # ---------- public APIs ----------

    async def cancel_stale_orders(self) -> Dict[str, List[Tuple[str, Any]]]:
        """
        Returns: {
          "ok":    [(order_id, response), ...],
          "fail":  [(order_id, Exception or error_msg), ...],
        }
        """
        markets: Dict[str, Any] = self._market_cache()
        results_ok: List[Tuple[str, Any]] = []
        results_fail: List[Tuple[str, Any]] = []

        try:
            orders = await self._clob.get_orders_retry()
        except Exception as e:
            return {"ok": [], "fail": [("get_orders", e)]}

        for o in orders:
            if o.get("status") != "LIVE":
                continue
            try:
                m = await self._get_market_cached(o["market"], markets)
                if not market_has_ended(m):
                    continue
                try:
                    resp = await self._clob.cancel_order_retry(o["id"])
                    results_ok.append((o["id"], resp))
                except Exception as e:
                    results_fail.append((o["id"], e))
            except Exception as e:
                results_fail.append((o.get("id", "?"), e))

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
            positions = await self._data.get_positions_retry()
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
                    resp = await self._data.redeem_position_retry(cid)
                    results_ok.append((cid, resp, p))
                except Exception as e:
                    results_fail.append((cid, e, p))
            except Exception as e:
                results_fail.append((cid or "?", e, p))

        return {"ok": results_ok, "fail": results_fail}

    async def place_order(self, context: MarketContext):
        for outcome, asset_id in context.outcomeAssets.items():
            enter_request = await self._get_enter_request(context.conditionId, asset_id)
            request = await self._evaluator.should_exit(context, outcome, enter_request) if enter_request else await self._evaluator.should_enter(context, outcome)
            if request:
                await self._store.add(request)

    async def _get_enter_request(self, market_id: str, asset_id: str):
        return await self._store.get(market_id, asset_id)

@lru_cache(maxsize=1)
def get_resolution_service() -> ResolutionService:
    return ResolutionService()


if __name__ == "__main__":
    keeper = ResolutionService()
    res = keeper.redeem_resolved_positions()
    print(res)