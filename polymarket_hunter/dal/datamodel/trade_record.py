from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class TradeRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="ignore")
    market_id: str
    asset_id: str
    side: str
    order_id: str
    slug: str
    outcome: str
    matched_amount: float = 0
    size: float = 0
    price: float = 0
    fee_rate_bps: Optional[float] = 0
    transaction_hash: Optional[str] = None
    trader_side: Optional[str] = None
    status: str = "LIVE"
    active: bool = True
    error: Optional[Any] = None
    raw_events: Optional[list[dict[str, Any]]] = Field(default_factory=list)
    event_type: str = "placement"
    matched_ts: Optional[float] = 0
    created_ts: float = Field(default_factory=time.time)
    updated_ts: float = Field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_ts = time.time()