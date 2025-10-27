from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel
from pydantic.config import ConfigDict


class MarketContext(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    conditionId: str
    slug: str
    question: str
    description: str
    resolutionSource: Optional[str]
    startDate: Optional[datetime]
    endDate: Optional[datetime]
    liquidity: float
    outcomes: list[str]
    clobTokenIds: list[str]
    outcomePrices: dict[str, dict[str, Any]]
    outcomeAssets: dict[str, str]
    tags: list[str]
