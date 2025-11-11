import time
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class MarketContext(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    condition_id: str
    slug: str
    question: str
    description: str
    resolution_source: Optional[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    liquidity: float
    order_min_size: float
    order_min_price_tick_size: float
    spread: float
    competitive: float
    one_hour_price_change: float
    one_day_price_change: float
    outcomes: list[str]
    clob_token_ids: list[str]
    outcome_prices: dict[str, dict[str, Any]]
    outcome_assets: dict[str, str]
    tags: set[str]
    event_ts: float = Field(default_factory=time.time)
    created_ts: float = Field(default_factory=time.time)
