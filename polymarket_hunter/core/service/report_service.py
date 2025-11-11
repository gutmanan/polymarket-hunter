from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Tuple

from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)
getcontext().prec = 28


@dataclass(frozen=True)
class TradeRow:
    market_id: str
    asset_id: str
    side: str            # "BUY" or "SELL"
    price: Decimal
    size: Decimal
    fee: Decimal         # 0 if missing
    ts: int              # seconds since epoch


def _parse_trades(rows: Any) -> List[TradeRow]:
    """Tolerant parser for Data API /trades rows."""
    out: List[TradeRow] = []
    for r in rows or []:
        try:
            ts_raw = int(r.get("timestamp") or 0)
            # accept ms or s
            ts_s = ts_raw // 1000 if ts_raw > 1_000_000_000_000 else ts_raw
            out.append(
                TradeRow(
                    market_id=str(r.get("conditionId") or r.get("market") or ""),
                    asset_id=str(r.get("asset") or r.get("token_id") or ""),
                    side=str(r.get("side") or "").upper(),
                    price=Decimal(str(r.get("price") or "0")),
                    size=Decimal(str(r.get("size") or "0")),
                    fee=Decimal(str(r.get("fee") or "0")),
                    ts=ts_s,
                )
            )
        except Exception as e:
            logger.warning("Skipping bad trade row %s (%s)", r, e)
    # stable sort by time; if equal, leave order (stable sort)
    out.sort(key=lambda t: t.ts)
    return out


class ReportService:
    def __init__(self):
        self.data = get_data_client()

    # -------- Wallet value --------

    def get_current_wallet_balance(self) -> Decimal:
        """
        Returns: USDC on-chain balance + portfolio totalValue (as requested).
        NOTE: Depending on /value semantics, this may double-count cash; this follows your spec.
        """
        usdc = Decimal(str(self.data.get_usdc_balance() or 0))
        value = self.data.get_portfolio_value()
        total_value = Decimal(str(value[0]["value"] or 0))
        return usdc + total_value

    # -------- FIFO core --------

    @staticmethod
    def _fifo_seed_inventory(before_trades: List[TradeRow]) -> Dict[str, List[Tuple[Decimal, Decimal]]]:
        """
        Build opening inventory layers per asset_id using FIFO from all trades BEFORE the window.
        Each layer is (qty, unit_cost).
        Fees are applied on buys (added to cost) and on sells (reduce realized later).
        """
        layers: Dict[str, List[Tuple[Decimal, Decimal]]] = {}
        for t in before_trades:
            aid = t.asset_id
            layers.setdefault(aid, [])
            if t.side == "BUY":
                # cost includes fee
                total_cost = (t.price * t.size) + t.fee
                unit_cost = total_cost / t.size if t.size > 0 else Decimal("0")
                layers[aid].append((t.size, unit_cost))
            elif t.side == "SELL":
                # consume layers
                remaining = t.size
                while remaining > 0 and layers[aid]:
                    q, c = layers[aid][0]
                    take = q if q <= remaining else remaining
                    if take == q:
                        layers[aid].pop(0)
                    else:
                        layers[aid][0] = (q - take, c)
                    remaining -= take
                # If remaining > 0 (short) we ignore — assuming no naked shorts on PM outcome tokens.
        return layers

    @staticmethod
    def _fifo_realized_pnl(period_trades: List[TradeRow],
                           layers: Dict[str, List[Tuple[Decimal, Decimal]]]) -> Decimal:
        """
        Compute realized PnL for trades IN the window using provided opening layers.
        Mutates `layers` (end-of-window inventory).
        """
        realized = Decimal("0")
        for t in period_trades:
            aid = t.asset_id
            layers.setdefault(aid, [])
            if t.side == "BUY":
                total_cost = (t.price * t.size) + t.fee
                unit_cost = total_cost / t.size if t.size > 0 else Decimal("0")
                layers[aid].append((t.size, unit_cost))
            else:  # SELL
                remaining = t.size
                sell_value = Decimal("0")
                buy_cost_value = Decimal("0")
                while remaining > 0 and layers[aid]:
                    q, c = layers[aid][0]
                    take = q if q <= remaining else remaining
                    buy_cost_value += take * c
                    sell_value += take * t.price
                    if take == q:
                        layers[aid].pop(0)
                    else:
                        layers[aid][0] = (q - take, c)
                    remaining -= take
                # realized from this SELL (apply sell fee)
                realized += (sell_value - buy_cost_value) - t.fee
        return realized

    # -------- PnL over window --------

    def compute_period_pnl(self, *, hours_back: int) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(hours=hours_back)
        end_dt = now
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # seed with trades BEFORE start
        before_rows = self.data.get_trades(querystring_params={"until": start_ts})
        before_trades = _parse_trades(before_rows)

        # trades within [start, end]
        period_rows = self.data.get_trades(querystring_params={"since": start_ts, "until": end_ts})
        period_trades = _parse_trades(period_rows)

        # Build opening inventory, then compute realized pnl for period
        layers = self._fifo_seed_inventory(before_trades)
        realized = self._fifo_realized_pnl(period_trades, layers)

        return {
            "window": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "hours": hours_back,
            },
            "trades_in_period": len(period_trades),
            "realized_pnl": str(realized),   # Decimal as string to avoid float issues
        }

    # -------- Human summary --------

    def generate_summary(self, *, hours_back: int) -> str:
        bal = self.get_current_wallet_balance()
        pnl = self.compute_period_pnl(hours_back=hours_back)
        return (
            f"📊 <b>Performance</b>\n"
            f"🕒 Window: {pnl['window']['start']} → {pnl['window']['end']} ({pnl['window']['hours']}h)\n"
            f"💼 Wallet (USDC + Portfolio): {bal}\n"
            f"🧾 Trades in period: {pnl['trades_in_period']}\n"
            f"💰 Realized PnL: <code>{pnl['realized_pnl']}</code>\n"
        )


if __name__ == "__main__":
    svc = ReportService()
    # sync-friendly usage (DataClient methods used here are sync)
    print(svc.generate_summary(hours_back=24))
