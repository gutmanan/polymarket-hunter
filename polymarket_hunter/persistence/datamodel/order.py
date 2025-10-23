import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Order:
    market_id: str
    asset_id: str
    outcome: str
    side: str
    price: float
    size: float
    status: str
    created_ts: float = field(default_factory=lambda: time.time())
    updated_ts: float = field(default_factory=lambda: time.time())
    extra: dict = field(default_factory=dict)
