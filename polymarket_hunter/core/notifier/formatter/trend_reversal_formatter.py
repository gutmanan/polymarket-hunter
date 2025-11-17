import time
from datetime import datetime

from polymarket_hunter.dal.datamodel.market_context import MarketContext
from polymarket_hunter.dal.datamodel.trend_prediction import TrendPrediction


def format_trend_reversal_message(context: MarketContext, outcome: str, trend: TrendPrediction) -> str:
    """
    Format a Telegram HTML message for a detected trend reversal.
    """
    if not trend.reversal or not trend.flipped_from:
        return ""

    emoji = "🔁"
    title = "Trend Reversal Detected"
    flipped = trend.flipped_from
    current = trend.direction
    conf = f"{trend.confidence:.2f}"
    t_stat = f"{trend.t_stat:.2f}"
    ts_str = datetime.utcfromtimestamp(trend.flipped_ts or time.time()).strftime("%Y-%m-%d %H:%M:%S UTC")

    arrow = "↑" if current == "UP" else "↓" if current == "DOWN" else "→"

    return (
        f"{emoji} <b>{title}</b>\n"
        f"📊 <b>{context.slug}</b>\n"
        f"📈 <b>Outcome:</b> {outcome}\n"
        f"↕ <b>Direction:</b> {flipped} → {current} {arrow}\n"
        f"📊 <b>T-Stat:</b> {t_stat} | <b>Confidence:</b> {conf}\n"
        f"⏰ <b>Detected:</b> {ts_str}"
    ).strip()
