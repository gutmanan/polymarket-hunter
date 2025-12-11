import time
from typing import Any, Dict

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.strategy_action import OrderType, Side
from polymarket_hunter.dal.datamodel.trade_error import TradeEvent, EventCode, EventState
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

    async def serve(self, payload: dict[str, Any]):
        if payload["action"] != "add":
            return

        try:
            req = OrderRequest.model_validate_json(payload["order"])
        except Exception as e:
            logger.warning("Invalid OrderRequest payload: %s", e, exc_info=True)
            return

        if req.order_type == OrderType.MARKET:
            res = self._clob.execute_market_order(
                token_id=req.asset_id,
                price=req.price,
                size=req.size,
                side=req.side,
                tif=req.tif
            )
        elif req.order_type == OrderType.LIMIT:
            res = self._clob.execute_limit_order(
                token_id=req.asset_id,
                price=req.price,
                size=req.size,
                side=req.side,
                tif=req.tif
            )
        else:
            raise NotImplementedError

        res["timestamp"] = time.time()
        is_success = bool(res.get("success"))

        if is_success:
            tr = self._build_trade_record(req, res)
            await self._deactivate_opposite(tr)
            await self._trade_store.add(tr)
        else:
            await TradeEvent.log(
                ctx=req.context,
                outcome=req.outcome,
                side=req.side,
                state=EventState.FAILED,
                request_source=req.request_source,
                strategy_name=req.strategy_name,
                rule_name=req.rule_name,
                code=EventCode.CLOB_API_ERROR,
                error=str(res.get("error", "Unknown error"))
            )

        if is_success == (req.side == Side.SELL):
            await self._order_store.remove(req.market_id, req.asset_id, Side.BUY)
        else:
            await self._order_store.remove(req.market_id, req.asset_id, Side.SELL)

    def _build_trade_record(self, req: OrderRequest, res: Dict[str, Any]) -> TradeRecord:
        market_id = req.market_id
        asset_id = req.asset_id
        side = req.side
        order_id = res.get("orderID")
        status = (res.get("status") or "").upper() or "LIVE"
        size_orig = float(res.get("makingAmount", 0) or 0) if side == Side.BUY else float(res.get("takingAmount", 0) or 0)
        size_mat = float(res.get("takingAmount", 0) or 0) if side == Side.BUY else float(res.get("makingAmount", 0) or 0)
        price = size_orig / size_mat if size_mat > 0 else 0

        return TradeRecord(
            market_id=market_id,
            asset_id=asset_id,
            side=side,
            order_id=order_id,
            slug=req.context.slug if req.context else '',
            outcome=req.outcome,
            matched_amount=size_mat,
            size=size_orig,
            price=price,
            transaction_hash=res.get("transactionsHashes")[0] if res.get("transactionsHashes") else None,
            trader_side="TAKER" if req.order_type == OrderType.MARKET else None,
            status=status,
            active=True,
            order_request=req,
            raw_events=[dict(res)],
            matched_ts=time.time()
        )

    async def _deactivate_opposite(self, tr):
        opposite_side = Side.BUY if tr.side == Side.SELL else Side.SELL
        existing_opposite = await self._trade_store.get_active(tr.market_id, tr.asset_id, opposite_side)
        if existing_opposite:
            deactivate = existing_opposite.model_copy(update={"active": False})
            deactivate.touch()
            await self._trade_store.update(deactivate)
