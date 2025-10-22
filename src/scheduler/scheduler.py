from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, Sequence
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

ET = ZoneInfo("America/New_York")
ASSETS: Iterable[str] = ("bitcoin", "ethereum", "solana", "xrp")

ResolveMarkets = Callable[[Sequence[str]], Awaitable[Sequence[Dict[str, Any]]]]


# ---------- time & slug utils ----------

def now_et() -> datetime:
    return datetime.now(tz=ET)

def start_of_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)

def next_hour(dt: datetime) -> datetime:
    return start_of_hour(dt) + timedelta(hours=1)

def format_slug(hour_et: datetime, asset: str) -> str:
    month = hour_et.strftime("%B").lower()
    day = str(hour_et.day)
    hour12 = hour_et.strftime("%I").lstrip("0") or "12"
    ampm = hour_et.strftime("%p").lower()
    return f"{asset}-up-or-down-{month}-{day}-{hour12}{ampm}-et"

def slugs_for_hour(hour_et: datetime) -> set[str]:
    return {format_slug(hour_et, a) for a in ASSETS}

def parse_iso_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


# ---------- housekeeping ops ----------

async def add_missing_current_hour(manager) -> None:
    want = slugs_for_hour(start_of_hour(now_et()))
    have = set(manager.get_slugs())
    missing = want - have
    if missing:
        await asyncio.gather(*(manager.add_slug(s) for s in sorted(missing)))

async def enqueue_next_hour(manager) -> None:
    target = next_hour(now_et())
    slugs = [format_slug(target, a) for a in ASSETS]
    await asyncio.gather(*(manager.add_slug(s) for s in slugs))

async def prune_expired(manager, resolve_markets: ResolveMarkets) -> None:
    slugs = sorted(manager.get_slugs())
    if not slugs:
        return

    markets = await resolve_markets(slugs)

    # choose the latest endDate per slug (defensive if multiple entries per slug)
    latest_by_slug: Dict[str, datetime] = {}
    for m in markets:
        slug = m.get("slug")
        end = parse_iso_utc(m.get("endDate") or m.get("endDateIso"))
        if not slug or not end:
            continue
        prev = latest_by_slug.get(slug)
        if not prev or end > prev:
            latest_by_slug[slug] = end

    nowu = datetime.now(timezone.utc)
    expired = [s for s, end in latest_by_slug.items() if end <= nowu]
    if expired:
        await asyncio.gather(*(manager.remove_slug(s) for s in expired))


# ---------- scheduler ----------

def build_scheduler(manager, resolve_markets: ResolveMarkets) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=ET)

    async def housekeeping():
        await prune_expired(manager, resolve_markets)
        await add_missing_current_hour(manager)

    async def at_55():
        await enqueue_next_hour(manager)

    sched.add_job(
        housekeeping,
        IntervalTrigger(minutes=1, timezone=ET),
        id="housekeeping",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60,
    )
    sched.add_job(
        at_55,
        CronTrigger(minute=55, second=0, timezone=ET),
        id="next-hour-slugs",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=120,
    )
    return sched
