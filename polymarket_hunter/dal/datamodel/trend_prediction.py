import time
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class Direction(StrEnum):
    FLAT = "FLAT"
    UP = "UP"
    DOWN = "DOWN"


class TrendPrediction(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    direction: Direction
    t_stat: float
    velocity: float
    confidence: float
    reversal: bool = False
    flipped_from: Optional[Direction] = None
    flipped_ts: Optional[float] = None
    created_ts: float = Field(default_factory=lambda: time.time())
    updated_ts: float = Field(default_factory=lambda: time.time())
