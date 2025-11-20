from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel, Column, DateTime


class MarketSnapshot(SQLModel, table=True):
    __tablename__ = "market_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)
    condition_id: str = Field(index=True, max_length=66)
    slug: str = Field(index=True)
    question: str
    description: str
    resolution_source: Optional[str] = Field(default=None)
    start_date: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    end_date: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    liquidity: Optional[float] = Field(default=None)
    order_min_size: Optional[float] = Field(default=None)
    order_min_price_tick_size: Optional[float] = Field(default=None)
    spread: Optional[float] = Field(default=None)
    competitive: Optional[float] = Field(default=None)
    one_hour_price_change: Optional[float] = Field(default=None)
    one_day_price_change: Optional[float] = Field(default=None)
    outcomes: List[str] = Field(sa_column=Column(JSONB))
    clob_token_ids: List[str] = Field(sa_column=Column(JSONB))
    outcome_assets: Dict[str, str] = Field(sa_column=Column(JSONB))
    outcome_prices: Dict[str, Any] = Field(sa_column=Column(JSONB))
    outcome_trends: Dict[str, Any] = Field(sa_column=Column(JSONB))
    tags: List[str] = Field(sa_column=Column(JSONB))
    event_ts: float = Field(index=True)
    created_ts: float
