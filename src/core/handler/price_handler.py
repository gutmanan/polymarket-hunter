import json
import threading
import time
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Callable, Optional, TypedDict

from py_clob_client.order_builder.constants import BUY, SELL

from src.config.settings import settings
from src.persistence.datamodel.order import Order
from src.persistence.order_store import RedisOrderStore
from src.core.handler.handlers import MessageHandler, MessageContext

TERMINAL_STATUSES = {"matched", "filled", "cancelled", "rejected", "failed"}
NON_TERMINAL_STATUSES = {"open", "live", "unmatched", "delayed", "partial"}


class PriceChangeHandler(MessageHandler):
    def __init__(self):
        # price_map[market_id][asset_id] -> {"outcome": str, "buy": float, "sell": float}
        self.price_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self.store = RedisOrderStore(settings.REDIS_URL)

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg.get("event_type") == "price_change"

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        self.update_prices(msg, ctx)
        market_id = msg["market"]

        for asset_id, asset in self.find_assets(market_id):
            existing_order = await self.store.get(market_id, asset_id)
            if asset and existing_order:
                if float(asset[SELL]) - float(existing_order.price) < -0.1:
                    print(f"{asset["outcome"]}: {existing_order.price} -> {asset[SELL]}")
                continue

        for asset_id, asset in self.find_assets(market_id, side=BUY, predicate=lambda p: 0.9 <= float(p) <= 0.99):
            order = Order(
                market_id=market_id,
                asset_id=asset_id,
                outcome=asset["outcome"],
                side=BUY,
                price=asset[BUY],
                size=1,
                status="open"
            )
            resp = await self.place_market_order(order)
            if resp:
                await self.store.update(market_id, asset_id, status="placed")

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
            asset_book[pc["side"]] = pc["price"]

    def find_assets(self, market_id: str, side: str = None, predicate: Callable[[float], bool] = None) -> List[Tuple[str, Dict[str, Any]]]:
        market_book = self.price_map.get(market_id, {})
        if not side:
            return list(market_book.items())

        results: List[Tuple[str, Dict[str, Any]]] = []
        for asset_id, obj in market_book.items():
            price = obj.get(side)
            if price is not None and predicate(price):
                results.append((asset_id, obj))
        return results

    # ---------- order lifecycle ----------

    async def place_market_order(self, order: Order) -> Dict[str, Any]:
        with self._lock:
            await self.store.add(order)

        # resp = ctx.clob_client.execute_market_order(
        #     token_id=asset_id,
        #     amount=amount,
        #     side=side,
        # )
        # print(f"placed order: {order}")
        return order.__dict__
