from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, Dict, Any, Optional

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from polymarket_hunter.constants import ET


class SchedulerTask(Protocol):

    @property
    def id(self) -> str: ...

    @property
    def trigger(self) -> BaseTrigger: ...

    @property
    def job_kwargs(self) -> Dict[str, Any]: ...

    async def run(self) -> None: ...


@dataclass
class BaseTask(ABC):
    _id: str
    misfire_grace_time: int = 60
    timezone: Any = field(default=ET)

    @property
    def id(self) -> str:
        return self._id

    @property
    def job_kwargs(self) -> Dict[str, Any]:
        return {
            "coalesce": True,
            "replace_existing": True,
            "misfire_grace_time": self.misfire_grace_time
        }

    @property
    @abstractmethod
    def trigger(self) -> BaseTrigger:
        ...

    @abstractmethod
    async def run(self) -> None:
        raise NotImplementedError


@dataclass
class IntervalTask(BaseTask):
    minutes: int = 0
    seconds: int = 0

    @property
    def trigger(self) -> BaseTrigger:
        return IntervalTrigger(minutes=self.minutes, seconds=self.seconds, timezone=self.timezone)


@dataclass
class DateTask(BaseTask):
    run_date: Optional[datetime] = None

    @property
    def trigger(self) -> BaseTrigger:
        return DateTrigger(run_date=self.run_date, timezone=self.timezone)


@dataclass
class CronTask(BaseTask):
    expr: str = None

    @property
    def trigger(self) -> BaseTrigger:
        return CronTrigger.from_crontab(expr=self.expr, timezone=self.timezone)
