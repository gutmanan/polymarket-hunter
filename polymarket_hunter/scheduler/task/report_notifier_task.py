from polymarket_hunter.core.service.report_service import ReportService
from polymarket_hunter.notifier.telegram_notifier import TelegramNotifier
from polymarket_hunter.scheduler.task.tasks import AbstractTask
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class ReportNotifierTask(AbstractTask):

    def __init__(self):
        self._reporter = ReportService()
        self._notifier = TelegramNotifier()

    @property
    def id(self) -> str:
        return "report-notifier"

    async def run(self):
        report = self._reporter.generate_report(hours_back=24)
        await self._notifier.send_message(report)

if __name__ == "__main__":
    import asyncio
    task = ReportNotifierTask()
    asyncio.run(task.run())