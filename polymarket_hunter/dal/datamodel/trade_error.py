import time
from enum import StrEnum
from typing import Any, Dict, Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel, Column

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy_action import Side
from polymarket_hunter.dal.db import write_object


class EventCode(StrEnum):
    TREND_FLAT = "TREND_FLAT"
    TREND_REVERSAL = "TREND_REVERSAL"
    TREND_MISMATCH = "TREND_MISMATCH"
    NO_ENTER = "NO_ENTER"
    NO_EXIT = "NO_EXIT"
    SLIPPAGE = "SLIPPAGE"
    LOCKOUT = "LOCKOUT"
    CLOB_API_ERROR = "CLOB_API_ERROR"
    EXCEPTION = "EXCEPTION"
    STRUCTURAL_ERROR = "STRUCTURAL_ERROR"
    MISSING_DATA_ERROR = "MISSING_DATA_ERROR"

class EventState(StrEnum):
    VALIDATED = "VALIDATED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class TradeEvent(SQLModel, table=True):
    __tablename__ = "trade_error"

    id: Optional[int] = Field(default=None, primary_key=True)
    market_id: str = Field(index=True, max_length=66)
    asset_id: str = Field(index=True)
    slug: str = Field(index=True)
    side: str
    outcome: str
    price: float = Field(description="Price at which block/fail occurred")
    code: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    state: str = Field(index=True)
    request_source: Optional[str] = Field(default=None)
    strategy_name: Optional[str] = Field(default=None)
    rule_name: Optional[str] = Field(default=None)
    additional_info: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    created_ts: float = Field(default_factory=time.time)

    @staticmethod
    async def log(
            ctx: MarketContext,
            outcome: str,
            side: Side,
            state: str,
            request_source: str,
            strategy_name: str,
            rule_name: str,
            code: Optional[str] = None,
            error: Optional[str] = None,
            additional_info: Optional[dict] = None
    ):
        event = TradeEvent(
            market_id=ctx.condition_id,
            asset_id=ctx.outcome_assets[outcome],
            slug=ctx.slug,
            side=side,
            outcome=outcome,
            price=float(ctx.outcome_prices[outcome][side]),
            code=code,
            error=error,
            state=state,
            request_source=request_source,
            strategy_name=strategy_name,
            rule_name=rule_name,
            additional_info=additional_info
        )
        await write_object(event)
