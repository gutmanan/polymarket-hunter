from typing import Optional

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy import Strategy, Rule
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side
from polymarket_hunter.utils.helper import time_left_sec, late_threshold_sec

CRYPTO_SPREAD = 0.03  # per-outcome spread cap for safer fills
NON_CRYPTO_SPREAD = 0.05
MIN_LIQ = 10_000_000_000  # skip illiquid books

CRYPTO_TAGS = {"Crypto"}
SPORT_TAGS = {"Sports"}
FINANCE_TAGS = {"Finance"}
PRICE_TAGS = {"Up or Down"}
INTERVAL_TAGS = {"1H", "4H"}

HIGH_RISK_TAGS = CRYPTO_TAGS | SPORT_TAGS | FINANCE_TAGS | PRICE_TAGS

# ---------- tag helpers ----------

def has_all(ctx: MarketContext, required: set[str]) -> bool:
    return required.issubset(ctx.tags)


def has_any(ctx: MarketContext, candidates: set[str]) -> bool:
    return bool(ctx.tags & candidates)


# ---------- time helpers ----------

def is_final_window(ctx: MarketContext, static_tf: Optional[float] = None, dynamic_tf: Optional[int] = None) -> bool:
    """
    Check if the time left is less than the late threshold.
    - static_tf: timeframe in seconds
    - dynamic_tf: the number of timeframes to use for the late threshold
    """
    if dynamic_tf:
        return time_left_sec(ctx) <= late_threshold_sec(ctx, dynamic_tf)
    elif static_tf:
        return time_left_sec(ctx) <= static_tf
    else:
        return False


# ---------- price helpers ----------

def price(ctx: MarketContext, outcome: str, side: Side):
    return float(ctx.outcome_prices.get(outcome, {}).get(side, 0) or 0)


def spread(ctx: MarketContext, outcome: str):
    b = price(ctx, outcome, Side.SELL)  # best_bid
    a = price(ctx, outcome, Side.BUY)  # best_ask
    return a - b if (a and b) else float("inf")


def ok_liquidity(ctx: MarketContext):
    return (ctx.liquidity >= MIN_LIQ) if ctx.liquidity else False


strategies = [
    Strategy(
        name="High Probability (Non-Crypto)",
        condition_fn=lambda ctx: (
                ok_liquidity(ctx)
                and not has_any(ctx, HIGH_RISK_TAGS)
        ),
        rules=[
            Rule(
                name="Buy Favorite (Yes)",
                condition_fn=lambda ctx: (
                        0.7 <= price(ctx, "Yes", Side.BUY) <= 0.9
                        and spread(ctx, "Yes") <= NON_CRYPTO_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="Yes"
                ),
            ),
            Rule(
                name="Buy Favorite (No)",
                condition_fn=lambda ctx: (
                        0.7 <= price(ctx, "No", Side.BUY) <= 0.9
                        and spread(ctx, "No") <= NON_CRYPTO_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="No"
                ),
            ),
        ],
    ),
]
