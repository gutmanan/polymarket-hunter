import time
from typing import Any, Dict

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.notifier.formatter.place_order_formatter import format_order_message
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.strategy_action import OrderType, Side
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class OrderService:

    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._order_store = RedisOrderRequestStore()
        self._trade_store = RedisTradeRecordStore()
        self._notifier = RedisNotificationStore()

    async def execute_order(self, payload: dict[str, Any]):
        if payload["action"] in {"add", "update"}:
            req = OrderRequest.model_validate_json(payload["order"])
            if req.action.order_type == OrderType.MARKET:
                res = self._clob.execute_market_order(
                    token_id=req.asset_id,
                    size=req.size,
                    side=req.side,
                    tif=req.action.time_in_force
                )
            elif req.action.order_type == OrderType.LIMIT:
                res = self._clob.execute_limit_order(
                    token_id=req.asset_id,
                    price=req.price,
                    size=req.size,
                    side=req.side,
                    tif=req.action.time_in_force
                )
            else:
                raise NotImplementedError

            trade = await self._trade_store.get(req.market_id, req.asset_id, req.side)
            if trade:
                trade = self._update_trade_record(trade, res)
                await self._trade_store.update(trade)

            is_success = bool(res.get("success"))
            if is_success == (req.side == Side.SELL):
                await self._order_store.remove(req.market_id, req.asset_id)

            if is_success:
                await self._notifier.send_message(format_order_message(req, res))

    # ---------- Helpers ----------

    def _update_trade_record(self, trade: TradeRecord, res: Dict[str, Any]) -> TradeRecord:
        return trade.model_copy(update={
            "order_id": res.get("orderID") or res.get("orderId"),
            "status": res.get("status", trade.status),
            "taking_amount": float(res.get("takingAmount") or 0),
            "making_amount": float(res.get("makingAmount") or 0),
            "txs": res.get("transactionsHashes") or res.get("transactionHashes") or [],
            "error": res.get("errorMsg") or res.get("error") or "",
            "raw": res,
            "updated_ts": time.time(),
        })
