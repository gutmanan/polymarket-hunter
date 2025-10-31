from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel
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
    outcomes: list[str]
    clob_token_ids: list[str]
    outcome_prices: dict[str, dict[str, Any]]
    outcome_assets: dict[str, str]
    tags: list[str]
