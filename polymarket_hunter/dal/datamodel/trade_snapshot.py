import time
from typing import Optional, Dict, Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel, Column


class TradeSnapshot(SQLModel, table=True):
    __tablename__ = "trade_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True)
    transaction_hash: Optional[str] = Field(index=True, default=None)
    market_id: str = Field(index=True, max_length=66)
    asset_id: str = Field(index=True)
    slug: str = Field(index=True)
    side: str
    outcome: str
    status: str = "LIVE"
    active: bool = True
    trader_side: Optional[str] = None
    matched_amount: Optional[float] = Field(default=0, description="Actual shares matched")
    price: float = Field(description="Actual price of the match/fill")
    fee_rate_bps: Optional[float] = 0
    request_source: str = Field(description="SL, TP, STRATEGY_ENTER, etc.")
    strategy_name: Optional[str] = Field(default=None)
    rule_name: Optional[str] = Field(default=None)
    strategy_action: Dict[str, Any] = Field(sa_column=Column(JSONB), description="Full StrategyAction used for entry/exit")
    matched_ts: Optional[float] = Field(index=True, default=0, description="Time of trade execution")
    created_ts: float = Field(default_factory=time.time)
