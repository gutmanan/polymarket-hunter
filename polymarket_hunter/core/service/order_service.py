import time
from typing import Any, Dict

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
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
        if payload["action"] not in {"add", "update"}:
            return

        try:
            req = OrderRequest.model_validate_json(payload["order"])
        except Exception as e:
            logger.warning("Invalid OrderRequest payload: %s", e, exc_info=True)
            return

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

        is_success = bool(res.get("success"))

        if is_success:
            tr = await self._build_trade_record(req, res)
            await self._trade_store.add(tr)

        """
        1. we remove the order from the order_store if it is a sell order and the order was successful. 
        2. we also remove the order from the order_store if it is a buy order and the order was not successful.
        * so we can try to sell again or buy again.
        """
        if is_success == (req.side == Side.SELL):
            await self._order_store.remove(req.market_id, req.asset_id)

    async def _build_trade_record(self, req: OrderRequest, res: Dict[str, Any]) -> ("TradeRecord"                                                                 ):
        market_id =req.market_id
        asset_id = req.asset_id
        side = req.side
        order_id = res.get("orderID")
        status = (res.get("status") or "").upper() or "LIVE"
        size_orig = float(res.get("makingAmount", 0))
        size_mat = float(res.get("takingAmount", 0))
        price = size_orig / size_mat if size_mat > 0 else 0

        return TradeRecord(
            market_id=market_id,
            asset_id=asset_id,
            side=side,
            order_id=order_id,
            slug=req.context.slug,
            outcome=req.outcome,
            matched_amount=size_mat,
            size=size_orig,
            price=price,
            transaction_hash=res.get("transactionsHashes")[0] if res.get("transactionsHashes") else None,
            trader_side="TAKER" if req.action.order_type == OrderType.MARKET else None,
            status=status,
            active=True,
            raw_events=[dict(res)],
            matched_ts=time.time()
        )
