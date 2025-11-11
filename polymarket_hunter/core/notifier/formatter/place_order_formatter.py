from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Optional

from polymarket_hunter.dal.datamodel.trade_record import TradeRecord


def _fmt_num(x: Optional[float], nd=3) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "—"

def _fmt_pct(filled: Optional[float], size: Optional[float]) -> str:
    try:
        if not size or size <= 0:
            return "—"
        r = max(min((filled or 0.0) / size, 1.0), 0.0)
        return f"{r*100:.0f}%"
    except Exception:
        return "—"

def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return "—"

def _header(tr: TradeRecord) -> str:
    if tr.error:
        return "❌ <b>Order Failed</b>"
    s = (tr.status or "").lower()
    filled_ok = (tr.matched_amount or 0) >= (tr.size or 0) > 0
    if s in {"matched", "filled", "success"} or filled_ok:
        return "✅ <b>Order Filled</b>"
    if tr.active and s in {"open", "pending", "booked", "partial", "partially_filled"}:
        return "⏳ <b>Order Pending</b>"
    return "📦 <b>Order Update</b>"

def format_trade_record_message(tr: TradeRecord) -> str:
    header = _header(tr)

    # Title
    slug = escape(tr.slug or "")
    outcome = escape(tr.outcome or "")
    title = f"📊 <b>{slug}</b>" + (f" — {outcome}" if outcome else "")

    # Intent
    side = escape((tr.side or "").upper())
    intent = f"🧭 <b>{side}</b> {_fmt_num(tr.size)} @ {_fmt_num(tr.price)}"

    # Fill / Notional / Fees
    filled = float(tr.matched_amount or 0.0)
    notional = filled * float(tr.price or 0.0)
    progress = f"📈 <b>Filled:</b> {_fmt_num(filled)} / {_fmt_num(tr.size)} ({_fmt_pct(tr.matched_amount, tr.size)})"
    amounts = [f"💰 <b>Notional (USDC):</b> {_fmt_num(notional, nd=2)}", f"🎟️ <b>Tokens:</b> {_fmt_num(filled)}"]

    fee_line = ""
    if tr.fee_rate_bps is not None:
        try:
            fee = notional * (float(tr.fee_rate_bps) / 10_000.0)
            fee_line = f"🧾 <b>Fee:</b> {_fmt_num(fee, nd=4)} ({_fmt_num(tr.fee_rate_bps, nd=2)} bps)"
        except Exception:
            pass

    # Status / IDs / Links / Time
    status = escape((tr.status or "UNKNOWN").upper())
    st = f"📦 <b>Status:</b> {status}"
    oid = f"🧾 <b>TX Hash:</b> <code>{escape(tr.transaction_hash or '')}</code>"
    tmatch = f"🕒 <b>Matched:</b> {_fmt_ts(tr.matched_ts)}"

    tx_line = ""
    if tr.transaction_hash:
        tx = escape(tr.transaction_hash)
        tx_line = f"🔗 <a href='https://polygonscan.com/tx/{tx}'>Polygonscan</a>"

    err_line = ""
    if tr.error:
        err_line = f"⚠️ <b>Error:</b> {escape(str(tr.error))[:500]}"

    parts = [
        header,
        title,
        intent,
        progress,
        "\n".join(amounts),
        fee_line,
        st,
        oid,
        tx_line,
        tmatch,
        err_line,
    ]
    return "\n".join(p for p in parts if p).strip() + "\n"
