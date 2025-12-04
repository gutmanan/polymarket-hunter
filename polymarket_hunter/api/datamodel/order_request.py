from typing import Optional

from pydantic import BaseModel

from polymarket_hunter.dal.datamodel.strategy_action import TIF, Side, OrderType


class ApiOrderRequest(BaseModel):
    slug: str
    outcome: str
    price: float
    size: float
    side: Side
    tif: Optional[TIF] = TIF.GTC
    order_type: Optional[OrderType] = OrderType.LIMIT
