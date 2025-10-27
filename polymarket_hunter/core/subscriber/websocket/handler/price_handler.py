import json
import threading
from typing import Dict, Any

from py_clob_client.order_builder.constants import BUY, SELL

from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.service.resolution_service import ResolutionService
from polymarket_hunter.core.strategy.strategy_evaluator import MarketContext
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore

TERMINAL_STATUSES = {"matched", "filled", "cancelled", "rejected", "failed"}
NON_TERMINAL_STATUSES = {"open", "live", "unmatched", "delayed", "partial"}


class PriceChangeHandler(MessageHandler):
    def __init__(self):
        # price_map[market_id][asset_id] -> {"outcome": str, "buy": float, "sell": float}
        self.price_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.store = RedisOrderRequestStore(settings.REDIS_URL)
        self._resolver = ResolutionService()
        self._lock = threading.Lock()

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg["event_type"] == "price_change"

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        self.update_prices(msg, ctx)
        context = self.build_context(ctx.markets[msg["market"]])
        await self._resolver.place_order(context)

    # ---------- pricing ----------

    def update_prices(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        market_id = msg["market"]
        market = ctx.markets[market_id]

        token_ids = json.loads(market["clobTokenIds"])
        outcomes = json.loads(market["outcomes"])

        market_book = self.price_map.setdefault(market_id, {})

        for pc in msg["price_changes"]:
            asset_id = pc["asset_id"]
            try:
                outcome = outcomes[token_ids.index(asset_id)]
            except ValueError:
                continue  # unknown asset_id, skip

            asset_book = market_book.setdefault(asset_id, {"outcome": outcome})
            asset_book[pc["side"]] = float(pc["price"])

    # ---------- context lifecycle ----------

    def build_context(self, market: dict[str, Any]):
        return MarketContext(
            conditionId=market["conditionId"],
            slug=market["slug"],
            question=market["question"],
            description=market["description"],
            resolutionSource=market["resolutionSource"],
            startDate=market["startDate"],
            endDate=market["endDate"],
            liquidity=market["liquidity"],
            outcomes=json.loads(market["outcomes"]),
            clobTokenIds=json.loads(market["clobTokenIds"]),
            outcomePrices=self.get_outcome_prices(market["conditionId"]),
            outcomeAssets=self.get_outcome_assets(market["conditionId"]),
            tags=[t["label"] for t in market["tags"]]
        )

    def get_outcome_prices(self, market_id: str) -> dict[str, dict[str, Any]]:
        return {
            data["outcome"]: {
                BUY: data[BUY] if BUY in data.keys() else 0,
                SELL: data[SELL] if SELL in data.keys() else 0
            } for asset_id, data in self.price_map[market_id].items()
        }

    def get_outcome_assets(self, market_id: str) -> dict[str, str]:
        return {
            data["outcome"]: asset_id for asset_id, data in self.price_map[market_id].items()
        }
