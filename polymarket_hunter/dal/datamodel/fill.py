from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Fill:
    market_id: str
    asset_id: str
    side: str
    price: Decimal
    size: Decimal
    fee: Decimal
    ts: int