import asyncio
import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OpenOrderParams, TradeParams
from py_clob_client.constants import POLYGON
from py_clob_client.exceptions import PolyApiException
from web3 import Web3

from polymarket_hunter.dal.datamodel.strategy_action import TIF
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import with_timeout, retryable

load_dotenv()
logger = setup_logger(__name__)


class CLOBClient:

    def __init__(self):
        self.clob_host = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
        self.private_key = os.getenv("PRIVATE_KEY")
        self.polygon_rpc = os.getenv("RPC_URL")
        self.chain_id = POLYGON

        if not self.private_key:
            raise RuntimeError("Missing PRIVATE_KEY in env")

        # web3 (for approvals/balances; PoA middleware for Polygon)
        self.w3 = Web3(Web3.HTTPProvider(self.polygon_rpc))
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address

        # CLOB client + optional API creds (if you’ve pre-created them)
        self.client = self._init_client()

        # Optional approvals (off by default)
        # self._init_approvals()

    # ---------- init helpers ----------

    def _init_client(self) -> ClobClient:
        client = ClobClient(self.clob_host, key=self.private_key, chain_id=self.chain_id)
        client.set_api_creds(client.create_or_derive_api_creds())
        return client

    def _init_approvals(self) -> None:
        """Wire ERC20/1155 approvals if you place on-chain via the exchange contracts.
           Left as a placeholder since most CLOB ops don’t need manual calls here."""
        pass

    # ---------- markets ----------

    @retryable()
    async def get_market_async(self, market_id: str):
        return await with_timeout(asyncio.to_thread(self.get_market, market_id), 10)

    def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        return self.client.get_market(condition_id=condition_id)

    # ---------- trades ----------

    @retryable()
    async def get_trade_async(self, trade_id: str):
        return await with_timeout(asyncio.to_thread(self.get_trade, trade_id), 10)

    def get_trade(self, trade_id: str):
        trades = self.client.get_trades(params=TradeParams(id=trade_id))
        if trades:
            return trades[0]
        return None

    # ---------- orders ----------

    @retryable()
    async def get_order_async(self, order_id: str):
        return await with_timeout(asyncio.to_thread(self.get_order, order_id), 10)

    def get_order(self, order_id: str):
        return self.client.get_order(order_id=order_id)

    @retryable()
    async def get_orders_async(self, market_id: Optional[str] = None, asset_id: Optional[str] = None):
        return await with_timeout(asyncio.to_thread(self.get_orders, market_id, asset_id), 10)

    def get_orders(self, market_id: Optional[str] = None, asset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if market_id or asset_id:
            params = OpenOrderParams(market=market_id, asset_id=asset_id)
            return self.client.get_orders(params=params)
        return  self.client.get_orders()

    @retryable()
    async def execute_limit_order_async(self, token_id: str, price: float, size: float, side: str, tif: TIF):
        return await with_timeout(asyncio.to_thread(self.execute_limit_order, token_id, price, size, side, tif), 10)

    def execute_limit_order(self, token_id: str, price: float, size: float, side: str, tif: TIF) -> Dict[str, Any]:
        """
        CLOB-native limit order. side: 0=BUY, 1=SELL (use py_clob_client.order_builder.constants BUY/SELL)
        """
        try:
            args = OrderArgs(token_id=token_id, price=price, size=size, side=side)
            signed = self.client.create_order(args)
            return self.client.post_order(signed, orderType=tif)
        except PolyApiException as e:
            logger.error(f"Unable to place limit order: {e}",)
            return {
                "success": False,
                "code": e.status_code,
                "error": e.error_msg
            }

    @retryable()
    async def execute_market_order_async(self, token_id: str, size: float, side: str, tif: TIF):
        return await with_timeout(asyncio.to_thread(self.execute_market_order, token_id, size, side, tif), 10)

    def execute_market_order(self, token_id: str, size: float, side: str, tif: TIF) -> Dict[str, Any]:
        """
        Market order: amount is the notional size in quote units the CLOB expects.
        """
        try:
            args = MarketOrderArgs(token_id=token_id, amount=size, side=side)
            logger.info(f"Market order args: {args}")
            signed = self.client.create_market_order(args)
            return self.client.post_order(signed, orderType=tif)
        except PolyApiException as e:
            logger.error(f"Unable to place market order: {e}")
            return {
                'success': False,
                "code": e.status_code,
                "error": e.error_msg
            }

    @retryable()
    async def cancel_order_async(self, order_id: str):
        return await with_timeout(asyncio.to_thread(self.cancel_order, order_id), 10)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an existing order by ID.
        """
        try:
            return self.client.cancel(order_id)
        except PolyApiException as e:
            logger.error(f"Unable to cancel order: {e}")
            return {
                "success": False,
                "code": e.status_code,
                "error": e.error_msg
            }

@lru_cache(maxsize=1)
def get_clob_client() -> CLOBClient:
    return CLOBClient()

if __name__ == "__main__":
    client = get_clob_client()
    # for o in client.get_orders():
    #     print(json.dumps(o))
    res = client.get_order("0x455b2c8f1cf468ccbf464863f34f2e3596ac2a61098ade18ec31c516a6736cf2")
    print(json.dumps(res))
    for tid in res["associate_trades"]:
        t = client.get_trade(tid)
        print(json.dumps(t))
