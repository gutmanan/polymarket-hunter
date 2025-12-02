import time
import uuid
from typing import Dict, Any

from polymarket_hunter.core.notifier.formatter.close_position_formatter import format_position_message
from polymarket_hunter.core.scheduler.tasks import BaseIntervalTask
from polymarket_hunter.core.service.resolution_service import get_resolution_service
from polymarket_hunter.dal.datamodel.strategy_action import Side
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeResolverTask(BaseIntervalTask):
    def __init__(self):
        super().__init__("_trade_resolver", minutes=5, misfire_grace_time=60)
        self._order_store = RedisOrderRequestStore()
        self._trade_store = RedisTradeRecordStore()
        self._resolver = get_resolution_service()
        self._notifier = RedisNotificationStore()

    async def _build_trade_record(self, pos: Dict[str, Any]) -> TradeRecord:
        market_id = pos["conditionId"]
        asset_id = pos["asset"]
        side = Side.SELL
        order_id = uuid.uuid4().hex
        status = "REDEEMED"
        size_orig = pos["size"]
        size_mat = pos["currentValue"]
        price = size_orig / size_mat if size_mat > 0 else 0
        req = await self._order_store.get(market_id, asset_id, Side.BUY)

        return TradeRecord(
            market_id=market_id,
            asset_id=asset_id,
            side=side,
            order_id=order_id,
            slug=pos["slug"],
            outcome=pos["outcome"],
            matched_amount=size_mat,
            size=size_orig,
            price=price,
            trader_side="TAKER",
            status=status,
            active=True,
            order_request=req,
            raw_events=[dict(pos)],
            event_type="resolution",
            matched_ts=time.time()
        )

    async def resolve_orders(self):
        res = await self._resolver.cancel_stale_orders()
        if res:
            for oid, r, order in res["ok"]:
                logger.info(f"Cancelled order: {order}")
            for oid, error, order in res["fail"]:
                logger.warning(f"Failed to cancel order: {error}")

    async def resolve_positions(self):
        res = await self._resolver.redeem_resolved_positions()
        if res:
            for cid, r, pos in res["ok"]:
                tr = await self._build_trade_record(pos)
                await self._trade_store.add(tr)
                await self._notifier.send_message(format_position_message(pos))
            for cid, error, pos in res["fail"]:
                logger.warning(f"Failed to redeem position: {error}")

    async def run(self):
        await self.resolve_orders()
        await self.resolve_positions()
