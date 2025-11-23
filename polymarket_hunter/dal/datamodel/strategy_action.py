from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel
from pydantic.config import ConfigDict


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TIF(StrEnum):
    GTC = "GTC"
    FOK = "FOK"
    GTD = "GTD"
    FAK = "FAK"


class StrategyAction(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    side: Side
    size: float
    outcome: str
    slippage: Optional[float] = 0.05
    stop_loss: Optional[float] = 1
    take_profit: Optional[float] = 1
    order_type: Optional[OrderType] = OrderType.MARKET
    time_in_force: Optional[TIF] = TIF.FOK
    cancel_on_conflict: bool = True
