from __future__ import annotations

import time
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side


class RequestType(StrEnum):
    STOP_LOSS = "Stop Loss"
    TAKE_PROFIT = "Take Profit"
    STRATEGY_ENTER = "Strategy Enter"
    STRATEGY_EXIT = "Strategy Exit"


class OrderRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="ignore")
    market_id: str
    asset_id: str
    outcome: str
    price: float
    size: float
    side: Side
    strategy_name: Optional[str]
    rule_name: Optional[str]
    request_type: Optional[RequestType]
    action: Optional[StrategyAction] = None
    context: Optional[MarketContext] = None
    created_ts: float = Field(default_factory=time.time)
    updated_ts: float = Field(default_factory=time.time)
