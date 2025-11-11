import asyncio
from datetime import datetime, timezone, time

from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.scheduler.tasks import BaseIntervalTask
from polymarket_hunter.utils.market import market_has_ended

ISOZ_FMT = "%Y-%m-%dT%H:%M:%SZ"


class HourlyMarketsTask(BaseIntervalTask):
    def __init__(self, slugs_subscriber):
        super().__init__("_daily_markets", minutes=5, misfire_grace_time=120)
        self._slugs_subscriber = slugs_subscriber
        self._data = get_data_client()
        self._gamma = get_gamma_client()

    async def get_current_markets(self):
        now = datetime.now(timezone.utc)
        now_iso = now.strftime(ISOZ_FMT)
        end = datetime.combine(now.date(), time(23, 59, 59, tzinfo=timezone.utc))
        end_iso = end.strftime(ISOZ_FMT)

        markets = await self._gamma.get_all_markets(
            params={
                'active': True,
                'closed': False,
                'archived': False,
                'include_tag': True,
                # 'tag_id': 101757, # Recurring markets tag id
                "end_date_min": now_iso,
                "end_date_max": end_iso,
                "order": "startDate",
                "ascending": False,
            }
        )
        return self._filtered_slugs(markets)

    async def add_missing_current_markets(self) -> None:
        want = await self.get_current_markets()
        have = set(self._slugs_subscriber.get_slugs())
        missing = want - have
        if missing:
            await asyncio.gather(*(self._slugs_subscriber.add_slug(s) for s in sorted(missing)))

    async def prune_expired(self) -> None:
        markets = await self._slugs_subscriber.get_markets()
        for m in markets:
            slug = m.get("slug")
            if not market_has_ended(m):
                continue

            await self._slugs_subscriber.remove_slug(slug)

    async def run(self):
        await self.add_missing_current_markets()
        await self.prune_expired()

    def _filtered_slugs(self, markets: list[dict]) -> set[str]:
        slugs = set()
        for m in markets:
            if bool(m.get("negRisk")):
                continue

            slug = m.get("slug")
            if not slug:
                continue

            tags = [t["label"] for t in m["tags"]]
            if any(tag in tags for tag in ("Sports", "15M")):
                continue

            slugs.add(slug)
        return slugs
