from __future__ import annotations

from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from polymarket_hunter.constants import ET
from polymarket_hunter.core.scheduler.crypto_markets_task import CryptoMarketsTask
from polymarket_hunter.core.scheduler.report_notifier_task import ReportNotifierTask
from polymarket_hunter.core.scheduler.tasks import SchedulerTask
from polymarket_hunter.core.scheduler.trade_resolver_task import TradeResolverTask


class SchedulerService:
    def __init__(self, slugs_subscriber) -> None:
        self._slugs_subscriber = slugs_subscriber
        self.scheduler = AsyncIOScheduler(timezone=ET)
        self.jobs = {}

    def add_jobs(self) -> None:
        tasks: List[SchedulerTask] = [
            CryptoMarketsTask(self._slugs_subscriber),
            TradeResolverTask(),
            ReportNotifierTask(),
        ]

        for t in tasks:
            self.scheduler.add_job(t.run, t.trigger, id=t.id, **t.job_kwargs)

    def start(self) -> None:
        if not self.scheduler.running:
            self.add_jobs()
            self.scheduler.start()

    def stop(self, wait: bool = False) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)

    def reload(self) -> None:
        self.scheduler.remove_all_jobs()
        self.add_jobs()
