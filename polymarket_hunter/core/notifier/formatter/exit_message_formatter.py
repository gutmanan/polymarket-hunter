from decimal import Decimal

from polymarket_hunter.dal.datamodel.market_context import MarketContext


def format_exit_message(context: MarketContext, outcome: str, entry_price: Decimal, current_price: Decimal, is_stop: bool):
    """
    Unified exit message formatter: stop loss / take profit.
    Returns HTML-formatted Telegram message.
    """
    diff = abs(entry_price - current_price)
    gain_loss_text = f"−{diff:.3f}" if is_stop else f"+{diff:.3f}"
    emoji = "🛑" if is_stop else "🎯"
    title = "Stop Loss Triggered" if is_stop else "Take Profit Reached"

    return (
        f"{emoji} <b>{title}</b>\n"
        f"📊 <b>{context.slug}</b>\n"
        f"📈 <b>Outcome:</b> {outcome}\n"
        f"💸 <b>Entry:</b> {entry_price:.3f} → <b>Exit:</b> {current_price:.3f}\n"
        f"📈 <b>Gain/Loss:</b> {gain_loss_text} USDC"
    ).strip()