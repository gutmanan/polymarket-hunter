from typing import Optional

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy import Strategy, Rule
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side
from polymarket_hunter.utils.helper import time_left_sec, late_threshold_sec

CRYPTO_SPREAD = 0.03  # per-outcome spread cap for safer fills
NON_CRYPTO_SPREAD = 0.05
MIN_LIQ = 10_000  # skip illiquid books

INTERVAL_TAGS = {"1H", "4H"}
CRYPTO_TAGS = {"Crypto", "Up or Down"}
SPORT_TAGS = {"Sports"}


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
    try:
        if "november-18" in ctx.slug:
            print(ctx.slug, ctx.liquidity, ctx.outcome_prices.get("Yes", {}).get("BUY", 0))
        return float(ctx.liquidity) >= MIN_LIQ
    except Exception:
        return False


strategies = [
    Strategy(
        name="Late-Expiry Favorite Clamp (Non-Crypto)",
        condition_fn=lambda ctx: (
                not has_any(ctx, CRYPTO_TAGS) and not has_any(ctx, SPORT_TAGS)
                and ok_liquidity(ctx)
        ),
        rules=[
            Rule(
                name="Buy Favorite (Yes)",
                condition_fn=lambda ctx: (
                        0.75 <= price(ctx, "Yes", Side.BUY) <= 0.90
                        and spread(ctx, "Yes") <= NON_CRYPTO_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="Yes",
                    stop_loss=0.20,
                    take_profit=0.15,
                ),
            ),
            Rule(
                name="Buy Favorite (No)",
                condition_fn=lambda ctx: (
                        0.75 <= price(ctx, "No", Side.BUY) <= 0.90
                        and spread(ctx, "No") <= NON_CRYPTO_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="No",
                    stop_loss=0.20,
                    take_profit=0.15,
                ),
            ),
        ],
    ),
]

# Strategy(
#     name="Late-Expiry Favorite Clamp (Crypto)",
#     condition_fn=lambda ctx: (
#             has_all(ctx, CRYPTO_TAGS) and has_any(ctx, INTERVAL_TAGS)
#             and ok_liquidity(ctx)
#             and is_final_window(ctx, dynamic_tf=2)
#     ),
#     rules=[
#         Rule(
#             name="Buy Favorite (Up)",
#             condition_fn=lambda ctx: (
#                     0.75 <= price(ctx, "Up", Side.BUY) <= 0.90
#                     and spread(ctx, "Up") <= CRYPTO_SPREAD
#             ),
#             action=StrategyAction(
#                 side=Side.BUY,
#                 size=10,
#                 outcome="Up",
#                 stop_loss=0.25,
#                 take_profit=0.10
#             ),
#         ),
#         Rule(
#             name="Buy Favorite (Down)",
#             condition_fn=lambda ctx: (
#                     0.75 <= price(ctx, "Down", Side.BUY) <= 0.90
#                     and spread(ctx, "Down") <= CRYPTO_SPREAD
#             ),
#             action=StrategyAction(
#                 side=Side.BUY,
#                 size=10,
#                 outcome="Down",
#                 stop_loss=0.25,
#                 take_profit=0.10
#             ),
#         ),
#     ],
# ),