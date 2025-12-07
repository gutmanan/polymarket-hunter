import asyncio
from typing import List, Dict, Any

from async_lru import alru_cache

from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.subscriber.websocket.observability_ws_client import SLUG_RESOLUTION_LATENCY
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class MarketResolver:
    def __init__(self):
        self._gamma = get_gamma_client()
        self._semaphore = asyncio.Semaphore(10)

    async def resolve(self, slugs: List[str]) -> List[Dict[str, Any]]:
        with SLUG_RESOLUTION_LATENCY.time():
            tasks = [self._fetch(slug) for slug in slugs]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_markets = []
        for slug, res in zip(slugs, results):
            if isinstance(res, Exception):
                logger.debug(f"Failed to resolve slug: '{slug}")
            elif res:
                valid_markets.append(res)

        return valid_markets

    @alru_cache(maxsize=2048, ttl=600)
    async def _fetch(self, slug: str) -> Dict[str, Any] | None:
        async with self._semaphore:
            return await self._gamma.get_market_by_slug(slug)
