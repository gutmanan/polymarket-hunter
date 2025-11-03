from typing import Any


def format_position_message(pos: dict[str, Any]):
    """
    Unified position message formatter: closed position.
    Returns HTML-formatted Telegram message.
    """
    return (
        f"📊 <b>{pos['title']}</b>\n"
        f"📈 <b>Outcome:</b> {pos['outcome']}\n"
        f"💰 <b>PnL:</b> {pos['cashPnl']:+.2f} USDC ({pos['percentPnl']:+.1f}%)\n"
        f"💵 <b>Size:</b> {pos['size']} @ {pos['avgPrice']:.3f} → {pos['curPrice']:.3f}"
    )
