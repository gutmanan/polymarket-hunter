from typing import Optional

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy import Strategy, Rule
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side
from polymarket_hunter.utils.helper import time_left_sec, late_threshold_sec

MAX_SPREAD = 0.05
MIN_LIQUIDITY = 1_000  # skip illiquid books

POLITICS_TAGS = {"Politics", "Geopolitics"}
CRYPTO_TAGS = {"Crypto"}
SPORT_TAGS = {"Sports"}
FINANCE_TAGS = {"Finance"}
PRICE_TAGS = {"Up or Down"}
INTERVAL_TAGS = {"15M", "1H", "4H"}

CRYPTO_UP_DOWN_TAGS = CRYPTO_TAGS | PRICE_TAGS


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


def has_min_liquidity(ctx: MarketContext):
    return (ctx.liquidity >= MIN_LIQUIDITY) if ctx.liquidity else False


# ---------- strategies ----------

def get_politics_strategy():
    return Strategy(
        name="High Probability (Politics)",
        condition_fn=lambda ctx: (
                has_min_liquidity(ctx)
                and has_any(ctx, POLITICS_TAGS)
        ),
        rules=[
            Rule(
                name="Buy Favorite (Yes)",
                condition_fn=lambda ctx: (
                        0.9 <= price(ctx, "Yes", Side.BUY) <= 0.99
                        and spread(ctx, "Yes") <= MAX_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=20,
                    outcome="Yes"
                ),
            ),
            Rule(
                name="Buy Favorite (No)",
                condition_fn=lambda ctx: (
                        0.9 <= price(ctx, "No", Side.BUY) <= 0.99
                        and spread(ctx, "No") <= MAX_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=20,
                    outcome="No"
                ),
            ),
        ],
    )


def get_crypto_strategy():
    return Strategy(
        name="High Probability (Crypto)",
        condition_fn=lambda ctx: (
                has_min_liquidity(ctx)
                and has_all(ctx, CRYPTO_UP_DOWN_TAGS)
                and has_any(ctx, INTERVAL_TAGS)
                and is_final_window(ctx, dynamic_tf=5)
        ),
        rules=[
            Rule(
                name="Buy Favorite (Up)",
                condition_fn=lambda ctx: (
                        0.98 <= price(ctx, "Up", Side.BUY)
                        and spread(ctx, "Up") <= MAX_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="Up",
                    stop_loss=0.1
                ),
            ),
            Rule(
                name="Buy Favorite (Down)",
                condition_fn=lambda ctx: (
                        0.98 <= price(ctx, "Down", Side.BUY)
                        and spread(ctx, "Down") <= MAX_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="Down",
                    stop_loss=0.1
                ),
            ),
        ],
    )


strategies = [
    get_politics_strategy(),
    get_crypto_strategy(),
]
