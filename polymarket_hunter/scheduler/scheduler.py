from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from polymarket_hunter.constants import ET
from polymarket_hunter.scheduler.task.crypto_markets_task import CryptoMarketsTask
from polymarket_hunter.scheduler.task.report_notifier_task import ReportNotifierTask
from polymarket_hunter.scheduler.task.trade_resolver_task import TradeResolverTask


def build_scheduler(manager) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=ET)
    trade_resolver = TradeResolverTask(manager)
    crypto_markets = CryptoMarketsTask(manager)
    report_notifier = ReportNotifierTask()

    sched.add_job(
        trade_resolver.run,
        IntervalTrigger(minutes=5, timezone=ET),
        id=trade_resolver.id,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60,
    )
    sched.add_job(
        crypto_markets.run,
        IntervalTrigger(minutes=1, timezone=ET),
        id=crypto_markets.id,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=120,
    )
    sched.add_job(
        report_notifier.run,
        IntervalTrigger(hours=1, timezone=ET),
        id=report_notifier.id,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60,
    )
    return sched
