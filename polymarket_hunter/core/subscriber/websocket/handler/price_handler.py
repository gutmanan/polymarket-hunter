import json
import threading
from typing import Dict, Any, Optional

from py_clob_client.order_builder.constants import BUY, SELL

from polymarket_hunter.core.strategy.strategy_evaluator import StrategyEvaluator
from polymarket_hunter.core.strategy.tend_detector import KalmanTrend
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.trend_prediction import TrendPrediction
from polymarket_hunter.utils.helper import q3, ts_to_seconds


class PriceChangeHandler(MessageHandler):
    def __init__(self):
        # price_map[market_id][asset_id] -> {"outcome": str, "buy": Decimal, "sell": Decimal}
        self._price_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._trend_detector = KalmanTrend()
        self._evaluator = StrategyEvaluator()
        self._lock = threading.Lock()

    event_types = ["price_change"]

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        ctx.logger.debug(f"Received price change: {msg}")
        market_id = msg["market"]
        market = ctx.markets.get(market_id)
        if market:
            self.update_prices(market, msg, ctx)
            self.update_trend(market, msg, ctx)
            context = self.build_context(market, msg)
            await self._evaluator.evaluate(context)

    # ---------- pricing ----------

    def update_prices(self, market: dict[str, Any], msg: Dict[str, Any], ctx: MessageContext) -> None:
        market_id = msg["market"]
        token_ids = json.loads(market["clobTokenIds"])
        outcomes = json.loads(market["outcomes"])

        with self._lock:
            market_book = self._price_map.setdefault(market_id, {})
            for pc in msg["price_changes"]:
                asset_id = pc["asset_id"]
                try:
                    outcome = outcomes[token_ids.index(asset_id)]
                except ValueError:
                    continue
                asset_book = market_book.setdefault(asset_id, {"outcome": outcome})
                best_ask = pc.get("best_ask")
                best_bid = pc.get("best_bid")
                if best_ask is not None:
                    asset_book[BUY] = q3(best_ask)
                if best_bid is not None:
                    asset_book[SELL] = q3(best_bid)

    def update_trend(self, market: dict[str, Any], msg: Dict[str, Any], ctx: MessageContext) -> None:
        market_id = msg["market"]
        ts = ts_to_seconds(msg.get("timestamp"))
        tick_size = market.get("orderPriceMinTickSize")

        with self._lock:
            market_book = self._price_map.get(market_id, {})
            for asset_id, data in market_book.items():
                ask, bid = map(lambda s: float(data.get(s, 0)), (BUY, SELL))
                if not (ask >= bid > 0):
                    continue

                mid, spread = (ask + bid) / 2, ask - bid
                key = f"{market_id}:{asset_id}"
                trend = self._trend_detector.update(key, mid=mid, spread=spread, ts=ts, tick_size=tick_size)
                prev: TrendPrediction = data.get("trend")
                if prev and trend.direction != prev.direction:
                    data["trend"] = trend.model_copy(update={
                        "reversal": True,
                        "flipped_from": prev.direction,
                        "flipped_ts": ts
                    })
                    continue

                data["trend"] = trend.model_copy(update={
                    "reversal": prev.reversal if prev else False,
                    "flipped_from": prev.flipped_from if prev else None,
                    "flipped_ts": prev.flipped_ts if prev else None
                })

    # ---------- context lifecycle ----------

    def build_context(self, market: dict[str, Any], msg: Dict[str, Any]):
        return MarketContext(
            condition_id=market["conditionId"],
            slug=market["slug"],
            question=market["question"],
            description=market["description"],
            resolution_source=market.get("resolutionSource"),
            start_date=market.get("eventStartTime") or market.get("startDate"),
            end_date=market.get("endDate"),
            liquidity=float(market.get("liquidity", 0)),
            order_min_size=market.get("orderMinSize", 1),
            order_min_price_tick_size=market.get("orderPriceMinTickSize", 0.01),
            spread=market.get("spread", 0),
            competitive=market.get("competitive", 1),
            one_hour_price_change=market.get("oneHourPriceChange", 0),
            one_day_price_change=market.get("oneDayPriceChange", 0),
            outcomes=json.loads(market["outcomes"]),
            clob_token_ids=json.loads(market["clobTokenIds"]),
            outcome_prices=self.get_outcome_prices(market["conditionId"]),
            outcome_assets=self.get_outcome_assets(market["conditionId"]),
            outcome_trends=self.get_outcome_trends(market["conditionId"]),
            tags=set([t["label"] for t in market["tags"]]),
            event_ts=msg["timestamp"]
        )

    def get_outcome_prices(self, market_id: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            if market_id not in self._price_map:
                return {}
            return {
                data["outcome"]: {
                    BUY: data[BUY] if BUY in data.keys() else 0,
                    SELL: data[SELL] if SELL in data.keys() else 0
                } for asset_id, data in self._price_map[market_id].items()
            }

    def get_outcome_assets(self, market_id: str) -> dict[str, str]:
        with self._lock:
            if market_id not in self._price_map:
                return {}
            return {
                data["outcome"]: asset_id for asset_id, data in self._price_map[market_id].items()
            }

    def get_outcome_trends(self, market_id: str) -> dict[str, Optional[TrendPrediction]]:
        with self._lock:
            if market_id not in self._price_map:
                return {}
            return {
                data["outcome"]: data.get("trend") for asset_id, data in self._price_map[market_id].items()
            }
