from typing import Any


def format_cancel_order_message(order: dict[str, Any]):
    """
    Unified order message formatter: cancelled/stale order.
    Returns HTML-formatted Telegram message.
    """
    original_size = float(order.get('original_size', 0))
    size_matched = float(order.get('size_matched', 0))
    remaining_size = original_size - size_matched

    price = float(order.get('price', 0))
    value_cancelled = remaining_size * price

    side_emoji = "🟢" if order['side'] == 'BUY' else "🔴"

    return (
        f"🧹 <b>Stale Order Cancelled</b>\n"
        f"{side_emoji} <b>Side:</b> {order['side']} {order['outcome']}\n"
        f"💵 <b>Cancelled:</b> {remaining_size:g} @ {price:.2f} (${value_cancelled:.2f})\n"
        f"🆔 <code>{order['id'][:8]}...</code>"
    )