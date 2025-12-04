from polymarket_hunter.core.scheduler.tasks import BaseIntervalTask
from polymarket_hunter.core.service.report_service import ReportService
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class ReportNotifierTask(BaseIntervalTask):
    def __init__(self):
        super().__init__("_report_notifier", minutes=60, misfire_grace_time=60)
        self._reporter = ReportService()
        self._notifier = RedisNotificationStore()

    async def run(self):
        report = await self._reporter.generate_summary(hours_back=240)
        await self._notifier.send_message(report)
