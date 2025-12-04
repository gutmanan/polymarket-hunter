from typing import Optional

from pydantic import BaseModel


class ApiOrderUpdateRequest(BaseModel):
    slug: str
    outcome: str
    slippage: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
