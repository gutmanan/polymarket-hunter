from __future__ import annotations

import time
from dataclasses import field
from typing import Optional

from pydantic import BaseModel
from pydantic.config import ConfigDict

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side


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
    action: Optional[StrategyAction] = None
    context: Optional[MarketContext] = None
    created_ts: float = field(default_factory=lambda: time.time())
    updated_ts: float = field(default_factory=lambda: time.time())
