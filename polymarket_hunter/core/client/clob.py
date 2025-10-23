import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType, OrderBookSummary
from py_clob_client.constants import POLYGON
from web3 import Web3

load_dotenv()

def parse_iso8601(s: str) -> datetime:
    """Python 3.10-friendly parse for timestamps like 2020-11-04T00:00:00Z."""
    if not s:
        # naive max future to pass "is_live"
        return datetime.max.replace(tzinfo=timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


class CLOBClient:
    """
    CLOB-first Polymarket client.

    - Uses py-clob-client exclusively.
    - No gamma endpoints.
    - Provides helpers to fetch/normalize markets & events, order book, prices, and place orders.
    """

    def __init__(
            self,
            clob_host: str = os.getenv("CLOB_HOST", "https://clob.polymarket.com"),
            chain_id: int = POLYGON,
            polygon_rpc: str = os.getenv("RPC_URL"),
            do_approvals: bool = False,
    ) -> None:
        self.clob_host = clob_host
        self.chain_id = chain_id
        self.private_key = os.getenv("PRIVATE_KEY")
        if not self.private_key:
            raise RuntimeError("Missing PRIVATE_KEY in env")

        # web3 (for approvals/balances; PoA middleware for Polygon)
        self.w3 = Web3(Web3.HTTPProvider(polygon_rpc))
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address

        # CLOB client + optional API creds (if you’ve pre-created them)
        self.client = self._init_client()

        # Known addresses
        self.exchange_address = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"

        # Optional approvals (off by default)
        if do_approvals:
            self._init_approvals()

    # ---------- init helpers ----------

    def _init_client(self) -> ClobClient:
        client = ClobClient(self.clob_host, key=self.private_key, chain_id=self.chain_id)
        client.set_api_creds(client.create_or_derive_api_creds())
        return client

    def _init_approvals(self) -> None:
        """Wire ERC20/1155 approvals if you place on-chain via the exchange contracts.
           Left as a placeholder since most CLOB ops don’t need manual calls here."""
        pass

    # ---------- mapping ----------

    @staticmethod
    def _safe_float(d: Dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            v = d.get(key, default)
            return float(v) if v is not None else default
        except Exception:
            return default

    # ---------- order book & prices ----------

    def get_orderbook(self, token_id: str) -> OrderBookSummary:
        return self.client.get_order_book(token_id)

    def get_mid_from_book(self, token_id: str) -> Optional[float]:
        ob = self.get_orderbook(token_id)
        try:
            best_bid = max(float(b.price) for b in ob.bids) if ob.bids else None
            best_ask = min(float(a.price) for a in ob.asks) if ob.asks else None
            if best_bid is None or best_ask is None:
                return None
            return round((best_bid + best_ask) / 2.0, 4)
        except Exception:
            return None

    def get_price(self, token_id: str, side: str) -> float:
        """Spot price helper (CLOB provides a lightweight endpoint)."""
        return float(self.client.get_price(token_id, side=side))

    # ---------- orders ----------

    def execute_limit_order(self, token_id: str, price: float, size: float, side: str) -> str:
        """
        CLOB-native limit order. side: 0=BUY, 1=SELL (use py_clob_client.order_builder.constants BUY/SELL)
        """
        args = OrderArgs(token_id=token_id, price=price, size=size, side=side)
        return self.client.create_and_post_order(args)

    def execute_market_order(self, token_id: str, amount: float, side: str, order_type: OrderType = OrderType.FOK) -> Dict[str, Any]:
        """
        Market order: amount is the notional size in quote units the CLOB expects.
        """
        args = MarketOrderArgs(token_id=token_id, amount=amount, side=side, order_type=order_type)
        signed = self.client.create_market_order(args)
        return self.client.post_order(signed, orderType=order_type)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an existing order by ID.
        """
        return self.client.cancel(order_id)
