import json
import time
import threading
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Callable, Optional, TypedDict
from src.ws.handler.handlers import MessageHandler, MessageContext
from py_clob_client.order_builder.constants import BUY, SELL


TERMINAL_STATUSES = {"matched", "filled", "cancelled", "rejected", "failed"}
NON_TERMINAL_STATUSES = {"open", "live", "unmatched", "delayed", "partial"}


class OpenBlock(TypedDict, total=False):
    """Unified shape for what's blocking placement: either an open order or an active position."""
    block_type: str               # "order" | "position"
    market_id: str
    asset_id: str
    side: str                     # for orders; optional/unknown for position
    status: str                   # order status OR "position"
    order_id: Optional[str]       # for orders
    size: Optional[Decimal]       # for positions
    created_at: Optional[float]
    source: str                   # "orders_map" | "positions_api"


class PriceChangeHandler(MessageHandler):
    def __init__(self):
        # price_map[market_id][asset_id] -> {"outcome": str, "buy": float, "sell": float}
        self.price_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # orders_map[(market_id, asset_id)] -> order info (only NON-terminal stay here)
        self.orders_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg.get("event_type") == "price_change"

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        self.update_prices(msg, ctx)
        market_id = msg["market"]
        predicate = lambda p: 0.7 <= float(p) <= 0.8
        matches = self.find_assets(market_id, side=BUY, predicate=predicate)

        for asset_id, _ in matches:
            if not self.can_place_order(ctx, market_id, asset_id):
                # Already have an open order OR a live position for this asset in this market
                continue

            # If you place, consider pessimistic marking to prevent double-fire in the same tick
            resp = self.place_market_order(ctx, market_id, asset_id, side=BUY, amount=1)
            self.update_orders_from_response(market_id, asset_id, side=BUY, response=resp)

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

    def find_assets(
            self,
            market_id: str,
            side: str,
            predicate: Callable[[float], bool]
    ) -> List[Tuple[str, Dict[str, Any]]]:
        market_book = self.price_map.get(market_id, {})
        results: List[Tuple[str, Dict[str, Any]]] = []
        for asset_id, obj in market_book.items():
            price = obj.get(side)
            if price is not None and predicate(price):
                results.append((asset_id, obj))
        return results

    # ---------- unified "open" guard (order OR position) ----------

    def can_place_order(self, ctx: MessageContext, market_id: str, asset_id: str) -> bool:
        """True iff there is no open order AND no active position for (market_id, asset_id)."""
        return self.get_open_block(ctx, market_id, asset_id) is None

    def get_open_block(self, ctx: MessageContext, market_id: str, asset_id: str) -> Optional[OpenBlock]:
        """
        Returns a normalized blocker dict if an open order exists (non-terminal)
        or if there is an active position from the Polymarket Data API.
        Otherwise returns None.
        """
        # 1) Check in-memory open order first
        with self._lock:
            order = self.orders_map.get((market_id, asset_id))

        if order:
            status = (order.get("status") or "").lower()
            if status in NON_TERMINAL_STATUSES or status not in TERMINAL_STATUSES:
                # Treat unknown status as non-terminal (defensive)
                return OpenBlock(
                    block_type="order",
                    market_id=market_id,
                    asset_id=asset_id,
                    side=str(order.get("side") or ""),
                    status=status or "open",
                    order_id=order.get("order_id"),
                    created_at=float(order.get("created_at") or time.time()),
                    source="orders_map",
                )

        # 2) Fallback to active positions (size > 0 for that asset)
        pos = self._fetch_active_position(ctx, market_id, asset_id)
        if pos is not None:
            # Result sample provided by you: size, title, outcome, redeemable, etc.
            size = Decimal(str(pos.get("size", "0")))
            if size > 0:
                return OpenBlock(
                    block_type="position",
                    market_id=market_id,
                    asset_id=asset_id,
                    side="",  # unknown; position could be net long this outcome
                    status="position",
                    order_id=None,
                    size=size,
                    created_at=None,
                    source="positions_api",
                )

        return None

    def _fetch_active_position(self, ctx: MessageContext, market_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        Query Data API for positions in this market and return the entry for this asset_id, if any.
        Expects a list like you pasted; be defensive about shapes.
        """
        try:
            results = ctx.data_client.get_positions(querystring_params={"market": [market_id]})
        except Exception:
            return None

        if not results or not isinstance(results, list):
            return None

        return next((item for item in results if item.get("asset") == asset_id), None)

    # ---------- order lifecycle ----------

    def place_market_order(
            self,
            ctx: MessageContext,
            market_id: str,
            asset_id: str,
            side: str,
            amount: float,
    ) -> Dict[str, Any]:
        """
        Pessimistically mark an open slot (non-terminal) to prevent duplicate placement in the same tick,
        call the API, return response.
        """
        with self._lock:
            self._mark_open_order_unlocked(market_id, asset_id, side, provisional=True, notes="pessimistic-open")

        resp = ctx.clob_client.execute_market_order(
            token_id=asset_id,
            amount=amount,
            side=side,
        )
        print(f"placed order: {resp}")
        return resp

    def update_orders_from_response(
            self,
            market_id: str,
            asset_id: str,
            side: str,
            response: Dict[str, Any]
    ) -> None:
        """
        Normalize & store the response.
        Example response:
        {
          'errorMsg': '',
          'orderID': '0x...',
          'takingAmount': '1.612902',
          'makingAmount': '0.999999',
          'status': 'matched',
          'transactionsHashes': ['0x...'],
          'success': True
        }
        """
        order_id = response.get("orderID")
        status = (response.get("status") or "").lower()
        success = bool(response.get("success"))
        taking = response.get("takingAmount")
        making = response.get("makingAmount")

        record = {
            "order_id": order_id,
            "market_id": market_id,
            "asset_id": asset_id,
            "side": side,
            "status": status or ("open" if success and not order_id else "failed"),
            "taking_amount": Decimal(str(taking)) if taking is not None else None,
            "making_amount": Decimal(str(making)) if making is not None else None,
            "tx_hashes": list(response.get("transactionsHashes") or []),
            "error": response.get("errorMsg") or None,
            "success": success,
            "created_at": time.time(),  # keep original insert time if you want; here we set/update
            "updated_at": time.time(),
        }

        with self._lock:
            self.orders_map[(market_id, asset_id)] = record
            # Free the slot if terminal (e.g., market order matched immediately)
            if status in TERMINAL_STATUSES:
                self.orders_map.pop((market_id, asset_id), None)

    def _mark_open_order_unlocked(self, market_id: str, asset_id: str, side: str, provisional: bool, notes: str = "") -> None:
        self.orders_map[(market_id, asset_id)] = {
            "order_id": None,
            "market_id": market_id,
            "asset_id": asset_id,
            "side": side,
            "status": "open" if provisional else "live",
            "taking_amount": None,
            "making_amount": None,
            "tx_hashes": [],
            "created_at": time.time(),
            "notes": notes,
        }

    # ---------- optional hygiene ----------

    def cleanup_stale_orders(self, ttl_seconds: float = 300.0) -> None:
        """
        Remove any non-terminal entries that look stuck or stale.
        Call periodically if needed.
        """
        now = time.time()
        with self._lock:
            to_delete = []
            for key, order in self.orders_map.items():
                status = (order.get("status") or "").lower()
                created = float(order.get("created_at") or now)
                if status not in NON_TERMINAL_STATUSES:
                    # Unknown status — be conservative and keep unless very stale
                    if now - created > ttl_seconds:
                        to_delete.append(key)
                elif now - created > ttl_seconds:
                    to_delete.append(key)
            for k in to_delete:
                self.orders_map.pop(k, None)
