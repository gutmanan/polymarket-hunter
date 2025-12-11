from polymarket_hunter.core.notifier.formatter.cancel_order_formatter import format_cancel_order_message
from polymarket_hunter.core.notifier.formatter.close_position_formatter import format_close_position_message
from polymarket_hunter.core.scheduler.tasks import IntervalTask
from polymarket_hunter.core.service.resolution_service import get_resolution_service
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeResolverTask(IntervalTask):
    def __init__(self):
        super().__init__("_trade_resolver", minutes=15)
        self._resolver = get_resolution_service()
        self._notifier = RedisNotificationStore()

    async def resolve_orders(self):
        res = await self._resolver.cancel_stale_orders()
        if res:
            for oid, r, order in res["ok"]:
                await self._notifier.send_message(format_cancel_order_message(order))
            for oid, error, order in res["fail"]:
                logger.warning(f"Failed to cancel order: {error}")

    async def resolve_positions(self):
        res = await self._resolver.redeem_resolved_positions()
        if res:
            for cid, r, pos in res["ok"]:
                await self._notifier.send_message(format_close_position_message(pos))
            for cid, error, pos in res["fail"]:
                logger.warning(f"Failed to redeem position: {error}")

    async def run(self):
        await self.resolve_orders()
        await self.resolve_positions()
