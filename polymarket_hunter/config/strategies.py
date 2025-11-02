from datetime import datetime, timezone

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.strategy import Strategy, Rule
from polymarket_hunter.dal.datamodel.strategy_action import StrategyAction, Side

EDGE = 0.981      # buy-both if asks sum < 98.1c (covers fees/slippage)
MAX_SPREAD = 0.02 # per-outcome spread cap for safer fills
MIN_LIQ = 500     # skip illiquid books

# ---------- time helpers ----------

def _now_s() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def _to_epoch_s(dt: datetime) -> int:
    return int(dt.timestamp())

def time_left_sec(ctx: MarketContext) -> int:
    return _to_epoch_s(ctx.end_date) - _now_s()

def duration_sec(ctx: MarketContext) -> int:
    return _to_epoch_s(ctx.end_date) - _to_epoch_s(ctx.start_date)

def late_threshold_sec(ctx: MarketContext) -> int:
    d = max(0, duration_sec(ctx))
    return d // 3  # final third

def in_final_third(ctx: MarketContext) -> bool:
    return time_left_sec(ctx) <= late_threshold_sec(ctx)

def before_final_third(ctx: MarketContext) -> bool:
    return time_left_sec(ctx) > late_threshold_sec(ctx)

# ---------- price helpers ----------

def price(ctx: MarketContext, outcome: str, side: Side):
    return float(ctx.outcome_prices.get(outcome, {}).get(side, 0) or 0)

def spread(ctx: MarketContext, outcome: str):
    b = price(ctx, outcome, Side.SELL)  # best_bid
    a = price(ctx, outcome, Side.BUY)   # best_ask
    return a - b if (a and b) else 9.99

def asks_sum(ctx: MarketContext):
    return price(ctx, "Up", Side.BUY) + price(ctx, "Down", Side.BUY)

def ok_liquidity(ctx: MarketContext):
    try:
        return float(ctx.liquidity) >= MIN_LIQ
    except Exception:
        return False

strategies = [
    # 1) Sum-of-asks mispricing (market-neutral entry): Buy BOTH when UpAsk + DownAsk < EDGE
    Strategy(
        name="Two-Leg Ask-Sum Arb",
        condition_fn=lambda ctx: (
            "Crypto" in ctx.tags
            and ok_liquidity(ctx)
            and price(ctx, "Up", Side.BUY) > 0 and price(ctx, "Down", Side.BUY) > 0
            and spread(ctx, "Up")   <= MAX_SPREAD
            and spread(ctx, "Down") <= MAX_SPREAD
            and asks_sum(ctx) < EDGE
            and before_final_third(ctx)
        ),
        rules=[
            Rule(
                name="Arb leg: Buy Up",
                condition_fn=lambda ctx: True,
                action=StrategyAction(
                    side=Side.BUY,
                    size=8,                 # keep sizes equal on both legs
                    outcome="Up",
                    stop_loss=0.1,          # 10c per-leg guard
                    take_profit=0.02        # scalp 2c per-leg
                )
            ),
            Rule(
                name="Arb leg: Buy Down",
                condition_fn=lambda ctx: True,
                action=StrategyAction(
                    side=Side.BUY,
                    size=8,
                    outcome="Down",
                    stop_loss=0.1,
                    take_profit=0.02
                )
            ),
        ],
    ),

    # 2) Late-expiry clamp (favorite near resolution with tight spread)
    Strategy(
        name="Late-Expiry Favorite Clamp",
        condition_fn=lambda ctx: (
            "Crypto" in ctx.tags
            and ok_liquidity(ctx)
            and before_final_third(ctx)
        ),
        rules=[
            Rule(
                name="Buy Favorite (Up)",
                condition_fn=lambda ctx: (
                    0.85 <= price(ctx, "Up", Side.BUY) <= 0.90
                    and spread(ctx, "Up") <= MAX_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="Up",
                    stop_loss=0.15,      # a sudden wick against you
                    take_profit=0.08    # grab a cent into resolution grind
                ),
            ),
            Rule(
                name="Buy Favorite (Down)",
                condition_fn=lambda ctx: (
                    0.85 <= price(ctx, "Down", Side.BUY) <= 0.90
                    and spread(ctx, "Down") <= MAX_SPREAD
                ),
                action=StrategyAction(
                    side=Side.BUY,
                    size=10,
                    outcome="Down",
                    stop_loss=0.15,
                    take_profit=0.08
                ),
            ),
        ],
    ),
]
