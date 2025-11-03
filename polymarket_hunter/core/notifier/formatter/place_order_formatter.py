from decimal import Decimal
from typing import Any

from polymarket_hunter.dal.datamodel.order_request import OrderRequest


def _as_dec(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")


def format_order_message(req: OrderRequest, res: dict[str, Any]) -> str:
    """
    Unified order message formatter: success / partial / pending / fail.
    Returns HTML-formatted Telegram message.
    """
    # Core fields
    success = bool(res.get("success"))
    status = str(res.get("status", "unknown")).lower()
    order_id = res.get("orderID") or res.get("orderId") or ""
    tx_hashes = res.get("transactionsHashes") or res.get("transactionHashes") or []
    tx_link = ""
    if tx_hashes:
        tx_link = f"<a href='https://polygonscan.com/tx/{tx_hashes[0]}'>View Transaction</a>"

    making = self._as_dec(res.get("makingAmount", "0"))
    taking = self._as_dec(res.get("takingAmount", "0"))

    price = req.price
    side = req.side
    size = req.size
    tif = req.action.time_in_force if req.action is not None else None

    # Optional enrichers (if present on your model)
    context = getattr(req, "context", None)
    market = getattr(context, "slug", None) or getattr(req, "market_id", None)
    outcome = getattr(req.action, "outcome", None)

    # Decorative header
    header = "✅ <b>Order Placed</b>"
    if not success:
        header = "❌ <b>Order Failed</b>"
    elif status in {"partial", "partially_filled", "open", "pending", "booked"}:
        header = "⏳ <b>Order Pending</b>"

    # Build the main lines
    title_line = ""
    if market and outcome:
        title_line = f"📊 <b>{market}</b> — {outcome}\n"
    elif market:
        title_line = f"📊 <b>{market}</b>\n"

    # side/size/price
    intent_line = f"🧭 <b>{side}</b> {size} @ {price:.3f}"
    if tif:
        intent_line += f" <i>({tif})</i>"

    # status/amounts (only show making/taking if non-zero or useful)
    status_line = f"📦 <b>Status:</b> {status.capitalize() if status != 'unknown' else '—'}"

    amounts = []
    if making > 0:
        amounts.append(f"💰 <b>Making:</b> {making.normalize():f}")
    if taking > 0:
        amounts.append(f"💵 <b>Taking:</b> {taking.normalize():f}")
    amounts_line = "\n".join(amounts)

    # order id / tx
    id_line = f"🧾 <b>Order ID:</b> <code>{order_id}</code>" if order_id else ""
    tx_line = f"🔗 {tx_link}" if tx_link else ""

    # Failure case
    if not success:
        err = res.get("errorMsg") or res.get("error") or "Unknown error"
        return (
            f"{header}\n"
            f"{title_line}"
            f"{intent_line}\n"
            f"⚠️ <b>Error:</b> {err}\n"
            f"{id_line}\n"
        ).strip()

    # Pending / Partial
    if status in {"partial", "partially_filled", "open", "pending", "booked"}:
        return (
            f"{header}\n"
            f"{title_line}"
            f"{intent_line}\n"
            f"{status_line}\n"
            f"{amounts_line}\n"
            f"{id_line}\n"
            f"{tx_line}"
        ).strip()

    # Success / Matched / Filled
    return (
        f"{header}\n"
        f"{title_line}"
        f"{intent_line}\n"
        f"{status_line}\n"
        f"{amounts_line}\n"
        f"{id_line}\n"
        f"{tx_line}"
    ).strip()
