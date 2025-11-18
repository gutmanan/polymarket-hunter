from typing import Optional

from pydantic import BaseModel

from polymarket_hunter.dal.datamodel.strategy_action import TIF, Side


class OrderRequest(BaseModel):
    slug: str
    outcome: str
    price: float
    size: float
    side: Side
    tif: Optional[TIF] = TIF.GTC
