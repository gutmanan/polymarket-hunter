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
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


# ---------- async & retry -------------

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


# ---------- time -------------

def parse_iso_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def utc_now_seconds() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def dt_to_seconds(dt: datetime) -> int:
    return int(dt.timestamp())


def ts_to_seconds(ts: float | int) -> float:
    ts = float(ts)
    return ts / 1000.0 if ts > 1e11 else ts


def time_left_sec(ctx: MarketContext) -> int:
    return dt_to_seconds(ctx.end_date) - utc_now_seconds()


def duration_sec(ctx: MarketContext) -> int:
    return dt_to_seconds(ctx.end_date) - dt_to_seconds(ctx.start_date)


def late_threshold_sec(ctx: MarketContext, tfs: int) -> int:
    d = max(0, duration_sec(ctx))
    return d // tfs


# ---------- price -------------

def q2(x): return Decimal(str(x)).quantize(Q2, rounding=ROUND_DOWN)


def q3(x): return Decimal(str(x)).quantize(Q3, rounding=ROUND_DOWN)


def q4(x): return Decimal(str(x)).quantize(Q4, rounding=ROUND_DOWN)


# ---------- market -------------

def market_has_ended(market: Dict[str, Any]):
    return parse_iso_utc(
        market.get("endDate") or
        market.get("endDateIso") or
        market.get("end_date") or
        market.get("end_date_iso")
    ) <= datetime.now(timezone.utc)
