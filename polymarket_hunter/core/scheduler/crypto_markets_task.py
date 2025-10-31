import asyncio
from datetime import datetime, timedelta
from typing import Iterable

from polymarket_hunter.constants import ET
from polymarket_hunter.core.scheduler.tasks import BaseIntervalTask
from polymarket_hunter.utils.market import market_has_ended

ASSETS: Iterable[str] = ("bitcoin", "ethereum", "solana", "xrp")


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


class CryptoMarketsTask(BaseIntervalTask):
    def __init__(self, slugs_subscriber):
        super().__init__("_crypto_markets", minutes=1, misfire_grace_time=120)
        self._slugs_subscriber = slugs_subscriber

    async def add_missing_current_hour(self) -> None:
        want = slugs_for_hour(start_of_hour(now_et()))
        have = set(self._slugs_subscriber.get_slugs())
        missing = want - have
        if missing:
            await asyncio.gather(*(self._slugs_subscriber.add_slug(s) for s in sorted(missing)))

    async def enqueue_next_hour(self) -> None:
        target = next_hour(now_et())
        want = set([format_slug(target, a) for a in ASSETS])
        have = set(self._slugs_subscriber.get_slugs())
        missing = want - have
        if missing:
            await asyncio.gather(*(self._slugs_subscriber.add_slug(s) for s in sorted(missing)))

    async def prune_expired(self) -> None:
        markets = await self._slugs_subscriber.get_markets()
        expired_slugs = [m["slug"] for m in markets if m.get("slug") and market_has_ended(m)]
        if expired_slugs:
            await asyncio.gather(*(self._slugs_subscriber.remove_slug(s) for s in expired_slugs))

    async def run(self):
        await self.add_missing_current_hour()
        await self.enqueue_next_hour()
        await self.prune_expired()
