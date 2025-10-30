from decimal import Decimal
from typing import Any

from py_clob_client.clob_types import OrderType

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.notifier.telegram_notifier import TelegramNotifier
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class OrderHandler:

    def __init__(self):
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._notifier = TelegramNotifier()

    async def handle(self, payload: dict[str, Any]):
        if payload["action"] in {"add", "update"}:
            request = OrderRequest.model_validate_json(payload["order"])
            resp = self._clob.execute_limit_order(
                token_id=request.asset_id,
                price=request.price,
                size=request.action.size,
                side=request.action.side,
                order_type=OrderType(request.action.time_in_force),
            )

            msg = self._format_order_message(resp, request)
            await self._notifier.send_message(msg)

    # ---------- Helpers ----------

    @staticmethod
    def _short(h: str, n: int = 10) -> str:
        return f"{h[:n]}..." if h and len(h) > n else h or ""

    @staticmethod
    def _as_dec(x: Any) -> Decimal:
        try:
            return Decimal(str(x))
        except Exception:
            return Decimal("0")

    def _format_order_message(self, resp: dict[str, Any], request: OrderRequest) -> str:
        """
        Unified order message formatter: success / partial / pending / fail.
        Returns HTML-formatted Telegram message.
        """
        # Core fields
        success = bool(resp.get("success"))
        status = str(resp.get("status", "unknown")).lower()
        order_id = resp.get("orderID") or resp.get("orderId") or ""
        tx_hashes = resp.get("transactionsHashes") or resp.get("transactionHashes") or []
        tx_link = ""
        if tx_hashes:
            tx_link = f"<a href='https://polygonscan.com/tx/{tx_hashes[0]}'>View Transaction</a>"

        # Amounts (as provided by API — semantics: making/taking are strings)
        making = self._as_dec(resp.get("makingAmount", "0"))
        taking = self._as_dec(resp.get("takingAmount", "0"))

        # From request (side, size, price, tif)
        # Try to get clean side label
        side = getattr(request.action.side, "name", str(request.action.side)).upper()
        size = request.action.size
        price = request.price
        tif = str(getattr(request.action, "time_in_force", "")) or str(getattr(request.action, "timeInForce", ""))

        # Optional enrichers (if present on your model)
        market = getattr(getattr(request, "context", None), "slug", None) or getattr(request, "market_id", None)
        outcome = getattr(request.action, "outcome", None)

        # Decorative header
        header = "✅ <b>Order Placed</b>"
        emoji = "✅"
        if not success:
            header = "❌ <b>Order Failed</b>"
            emoji = "❌"
        elif status in {"partial", "partially_filled", "open", "pending", "booked"}:
            header = "⏳ <b>Order Pending</b>"
            emoji = "⏳"

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
        id_line = f"🧾 <b>Order ID:</b> <code>{self._short(order_id)}</code>" if order_id else ""
        tx_line = f"🔗 {tx_link}" if tx_link else ""

        # Failure case
        if not success:
            err = resp.get("errorMsg") or resp.get("error") or "Unknown error"
            return (
                f"{header}\n"
                f"{title_line}"
                f"{intent_line}\n"
                f"⚠️ <b>Error:</b> {err}\n"
                f"{id_line}\n"
            ).strip()

        # Pending / Partial
        if status in {"partial", "partially_filled", "open", "pending", "booked"}:
            # If you know requested notional, you could compute fill %, but we keep it generic here.
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
