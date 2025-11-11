import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict

from py_clob_client.exceptions import PolyApiException
from tenacity import (retry, stop_after_attempt, wait_random_exponential, retry_if_exception, retry_if_exception_type,
                      before_sleep_log)

from polymarket_hunter.constants import Q2, Q4, Q3
from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy_action import Side
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

def _is_retryable_poly(e: BaseException) -> bool:
    if not isinstance(e, PolyApiException):
        return False
    code = getattr(e, "status_code", None)
    # retry on infra/rate-limit; fail fast on other 4xx
    return code is not None and (code >= 500 or code == 429)

def retryable():  # common decorator config
    return retry(
        retry=(retry_if_exception(_is_retryable_poly) | retry_if_exception_type(asyncio.TimeoutError)),
        wait=wait_random_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(5),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )

async def with_timeout(coro, seconds: float = 10.0):
    async with asyncio.timeout(seconds):
        return await coro

def market_has_ended(market: Dict[str, Any]):
    return parse_iso_utc(
        market.get("endDate") or
        market.get("endDateIso") or
        market.get("end_date") or
        market.get("end_date_iso")
    ) <= datetime.now(timezone.utc)

def parse_iso_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def _now_s() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def _to_epoch_s(dt: datetime) -> int:
    return int(dt.timestamp())

def time_left_sec(ctx: MarketContext) -> int:
    return _to_epoch_s(ctx.end_date) - _now_s()

def duration_sec(ctx: MarketContext) -> int:
    return _to_epoch_s(ctx.end_date) - _to_epoch_s(ctx.start_date)

def late_threshold_sec(ctx: MarketContext, tfs: int) -> int:
    d = max(0, duration_sec(ctx))
    return d // tfs

# ---------- price -------------

def q2(x): return Decimal(str(x)).quantize(Q2, rounding=ROUND_DOWN)

def q3(x): return Decimal(str(x)).quantize(Q3, rounding=ROUND_DOWN)

def q4(x): return Decimal(str(x)).quantize(Q4, rounding=ROUND_DOWN)

def prepare_market_amount(side: str, price: Decimal, size: float) -> float:
    """
    For BUY: desired is intended USDC budget.
    For SELL: desired is intended share quantity.
    Returns tuple: (amount_for_api_str, shares_str, usdc_str)
    """
    if side == Side.BUY:
        shares = q4(size)
        usdc_effective = q2(shares * price)
        ensure_dp_strict(usdc_effective, 2)
        return to_float(usdc_effective)
    elif side == Side.SELL:
        shares = q4(size)
        ensure_dp_strict(shares, 4)
        return to_float(shares)
    else:
        raise ValueError("side must be 'BUY' or 'SELL'")

def to_float(d: Decimal) -> float:
    return float(format(d, "f"))

def ensure_dp_strict(val: Decimal, max_dp: int):
    s = format(val, "f")
    if "." in s and len(s.split(".")[1]) > max_dp:
        raise ValueError(f"too many decimals: {s} (> {max_dp})")