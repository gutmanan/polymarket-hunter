import asyncio
from typing import Any

from aiolimiter import AsyncLimiter

from polymarket_hunter.core.scheduler.tasks import BaseDateTask
from polymarket_hunter.core.service.genai_service import GenAIService
from polymarket_hunter.dal.db import write_object
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class AnalyzeMarketsTask(BaseDateTask):
    def __init__(self, slugs_subscriber):
        super().__init__("_analyze_markets", date=None, misfire_grace_time=120)
        self._slug_subscriber = slugs_subscriber
        self._genai_service = GenAIService()
        self._semaphore = asyncio.Semaphore(100)
        self._rate_limiter = AsyncLimiter(max_rate=900, time_period=60)

    async def analyze_current_markets(self):
        logger.info("Fetching markets for analysis...")
        markets = await self._slug_subscriber.get_markets()
        logger.info(f"Found {len(markets)} markets. Starting parallel analysis...")
        tasks = [self._process_single_market(market) for market in markets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed = [r for r in results if r is not None and not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]
        logger.info(f"Batch Complete. Processed: {len(processed)}, Errors: {len(errors)}")

    async def _process_single_market(self, market: dict[str, Any]):
        async with self._semaphore:
            async with self._rate_limiter:
                try:
                    analysis = await self._genai_service.analyze_market(market)
                    if analysis:
                        await write_object(analysis)
                        logger.info(f"✅ Analyzed: {analysis.slug} -> {analysis.recommended_action}")
                        return analysis
                except Exception as e:
                    logger.error(f"Error processing {market.get('slug')}: {e}")
                    return e
        return None

    async def run(self):
        await self.analyze_current_markets()
