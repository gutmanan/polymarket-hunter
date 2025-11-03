from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from polymarket_hunter.dal.datamodel.strategy_action import TIF, OrderType, Side


class TradeRecord(BaseModel):
    id: str
    market_id: str
    asset_id: str
    outcome: str
    side: Side
    strategy: Optional[str] = None
    rule: Optional[str] = None

    # --- snapshot metrics ---
    spread: float
    liquidity: float
    competitive: float
    one_hour_price_change: float
    one_day_price_change: float

    # --- intent ---
    price: float
    size: float
    order_type: OrderType
    tif: TIF

    # --- exchange & exec ---
    order_id: Optional[str] = None
    status: str = "created"
    taking_amount: float = 0.0
    making_amount: float = 0.0
    txs: List[str] = Field(default_factory=list)

    # --- audit ---
    error: Optional[Any] = None
    raw: Optional[Dict[str, Any]] = None
    ingested_ts: Optional[float] = None
    evaluated_ts: Optional[float] = None
    created_ts: float = Field(default_factory=time.time)
    updated_ts: float = Field(default_factory=time.time)
