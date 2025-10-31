from polymarket_hunter.core.scheduler.tasks import BaseIntervalTask
from polymarket_hunter.core.service.resolution_service import get_resolution_service
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeResolverTask(BaseIntervalTask):
    def __init__(self):
        super().__init__("_trade_resolver", minutes=5, misfire_grace_time=60)
        self._resolver = get_resolution_service()
        self._notifier = RedisNotificationStore()

    async def resolve_orders(self):
        res = await self._resolver.cancel_stale_orders()
        if res:
            for order in res["ok"]:
                logger.info(f"Cancelled order: {order}")
            for order in res["fail"]:
                logger.warning(f"Failed to cancel order: {order}")

    async def resolve_positions(self):
        res = await self._resolver.redeem_resolved_positions()
        if res:
            for cid, resp, pos in res["ok"]:
                msg = (
                    f"📊 <b>{pos['title']}</b>\n"
                    f"📈 <b>Outcome:</b> {pos['outcome']}\n"
                    f"💰 <b>PnL:</b> {pos['cashPnl']:+.2f} USDC ({pos['percentPnl']:+.1f}%)\n"
                    f"💵 <b>Size:</b> {pos['size']} @ {pos['avgPrice']:.3f} → {pos['curPrice']:.3f}"
                )
                await self._notifier.send_message(msg)
            for cid, error, pos in res["fail"]:
                logger.warning(f"Failed to redeem position: {error}")

    async def run(self):
        await self.resolve_orders()
        await self.resolve_positions()
