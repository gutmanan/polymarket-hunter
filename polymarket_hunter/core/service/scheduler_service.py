from __future__ import annotations

from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from polymarket_hunter.constants import ET
from polymarket_hunter.core.scheduler.hourly_markets_task import HourlyMarketsTask
from polymarket_hunter.core.scheduler.report_notifier_task import ReportNotifierTask
from polymarket_hunter.core.scheduler.tasks import SchedulerTask
from polymarket_hunter.core.scheduler.trade_resolver_task import TradeResolverTask


class SchedulerService:
    def __init__(self, slugs_subscriber) -> None:
        self._slugs_subscriber = slugs_subscriber
        self._scheduler = AsyncIOScheduler(timezone=ET)
        self._jobs = {}

    def add_jobs(self) -> None:
        tasks: List[SchedulerTask] = [
            HourlyMarketsTask(self._slugs_subscriber),
            # AnalyzeMarketsTask(self._slugs_subscriber),
            TradeResolverTask(),
            ReportNotifierTask(),
        ]

        for t in tasks:
            self._scheduler.add_job(t.run, t.trigger, id=t.id, **t.job_kwargs)

    def start(self) -> None:
        if not self._scheduler.running:
            self.add_jobs()
            self._scheduler.start()

    def stop(self, wait: bool = False) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    def reload(self) -> None:
        self._scheduler.remove_all_jobs()
        self.add_jobs()
