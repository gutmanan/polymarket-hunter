from typing import Any

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.market_snapshot import MarketSnapshot
from polymarket_hunter.dal.db import write_object
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class ContextService:

    async def serve(self, payload: dict[str, Any]):
        try:
            context = MarketContext.model_validate_json(payload["context"])
        except Exception as e:
            logger.error(f"Failed to validate context payload: {e}")
            return

        snapshot = self._build_snapshot(context)
        await write_object(snapshot)

    def _build_snapshot(self, context: MarketContext) -> MarketSnapshot:
        return MarketSnapshot(
            condition_id=context.condition_id,
            slug=context.slug,
            question=context.question,
            description=context.description,
            resolution_source=context.resolution_source,
            start_date=context.start_date,
            end_date=context.end_date,
            liquidity=context.liquidity,
            order_min_size=context.order_min_size,
            order_min_price_tick_size=context.order_min_price_tick_size,
            spread=context.spread,
            competitive=context.competitive,
            one_hour_price_change=context.one_hour_price_change,
            one_day_price_change=context.one_day_price_change,
            outcomes=context.outcomes,
            clob_token_ids=context.clob_token_ids,
            outcome_assets=context.outcome_assets,
            outcome_prices=context.outcome_prices,
            outcome_trends={k: v.model_dump() if v else None for k, v in context.outcome_trends.items()},
            tags=[tag for tag in context.tags],
            event_ts=context.event_ts,
            created_ts=context.created_ts
        )
