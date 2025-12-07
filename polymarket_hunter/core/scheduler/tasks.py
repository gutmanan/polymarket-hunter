from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Dict, Any

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from polymarket_hunter.constants import ET


class SchedulerTask(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def trigger(self) -> BaseTrigger: ...

    @property
    def job_kwargs(self) -> Dict[str, Any]: ...  # optional extras (misfire, etc.)

    async def run(self) -> None: ...


@dataclass
class BaseIntervalTask:
    _id: str
    minutes: int
    misfire_grace_time: int = 60
    timezone = ET

    @property
    def id(self) -> str: return self._id

    @property
    def trigger(self) -> BaseTrigger:
        return IntervalTrigger(minutes=self.minutes, timezone=self.timezone)

    @property
    def job_kwargs(self) -> Dict[str, Any]:
        return {"coalesce": True, "replace_existing": True, "misfire_grace_time": self.misfire_grace_time}

    async def run(self) -> None:
        raise NotImplementedError


@dataclass
class BaseDateTask:
    _id: str
    date: datetime = None
    misfire_grace_time: int = 60
    timezone = ET

    @property
    def id(self) -> str:
        return self._id

    @property
    def trigger(self) -> BaseTrigger:
        return DateTrigger(run_date=self.date, timezone=self.timezone)

    @property
    def job_kwargs(self) -> Dict[str, Any]:
        return {"coalesce": True, "replace_existing": True, "misfire_grace_time": self.misfire_grace_time}

    async def run(self) -> None:
        raise NotImplementedError
