from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from typing import Dict, List, Tuple, Optional, Any

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.fill import Fill
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import market_has_ended, parse_iso_utc, q2

getcontext().prec = 28
logger = setup_logger(__name__)

class ReportService:
    def __init__(self):
        self.clob = get_clob_client()
        self.data = get_data_client()
        self.gamma = get_gamma_client()
        self._market_cache_by_id: Dict[str, dict] = {}

    # ---------- Market helpers ----------

    def _get_market(self, market_id: Optional[str]) -> Optional[dict]:
        if not market_id:
            return None
        if market_id in self._market_cache_by_id:
            return self._market_cache_by_id[market_id]
        try:
            m = self.clob.get_market(market_id)
            if isinstance(m, dict):
                self._market_cache_by_id[market_id] = m
            return m
        except Exception:
            return None

    @staticmethod
    def _is_asset_winning(market: dict, asset_id: str) -> Optional[str]:
        try:
            tokens = market.get("tokens", [])
            return next((t["winner"] for t in tokens if t["token_id"] == asset_id), None)
        except Exception:
            return None

    # ---------- Data fetching ----------

    def _fetch_all_fills_upto(self, end_ts_s: int) -> List[Fill]:
        fills: List[Fill] = []

        def parse_rows(rows) -> List[Fill]:
            out: List[Fill] = []
            for r in rows or []:
                try:
                    ts_raw = int(r.get("timestamp") or 0)
                    ts_s = ts_raw // 1000 if ts_raw > 1_000_000_000_000 else ts_raw
                    out.append(
                        Fill(
                            market_id=r["conditionId"],
                            asset_id=r["asset"],
                            side=r["side"],
                            price=Decimal(r["price"]),
                            size=Decimal(r["size"]),
                            fee=Decimal(r.get("fee", 0)),
                            ts=ts_s
                        )
                    )
                except Exception as e:
                    logger.error(f"ERROR parsing fill row: {r}. Skipping. Error: {e}")
            return out

        def page(before_val: int) -> List[Fill]:
            rows = self.data.get_trades(querystring_params={"until": before_val})
            return parse_rows(rows)

        cursors = [end_ts_s * 1000, end_ts_s]
        seen = set()

        for before_cursor in cursors:
            current_cursor = before_cursor
            got_any = False

            for _ in range(1000):
                chunk = page(current_cursor)
                if not chunk:
                    break

                got_any = True
                for f in chunk:
                    unique_key = (f.asset_id, f.ts, f.size, f.price, f.side)
                    if f.ts <= end_ts_s and unique_key not in seen:
                        fills.append(f)
                        seen.add(unique_key)

                oldest_ts = min(c.ts for c in chunk) if chunk else 0
                next_cursor = oldest_ts * 1000 if current_cursor > 1_000_000_000_000 else oldest_ts
                if oldest_ts == 0 or next_cursor >= current_cursor:
                    break
                current_cursor = next_cursor

            if got_any:
                break

        fills.sort(key=lambda x: x.ts)
        return fills

    def _fetch_closed_pnl(self, start_ts: int, end_ts: int) -> Decimal:
        try:
            closed_positions: List[Dict[str, Any]] = self.data.get_closed_positions()
            total_realized_pnl = Decimal("0")
            for pos in closed_positions:
                pnl_str = pos.get("realizedPnl")
                end_date = pos.get("endDate")
                if end_date is None:
                    continue
                end_ts_pos = int(parse_iso_utc(end_date).timestamp())
                if start_ts < end_ts_pos < end_ts and pnl_str is not None:
                    total_realized_pnl += Decimal(str(pnl_str))
            return total_realized_pnl
        except Exception as e:
            logger.warning(f"WARNING: Could not fetch closed positions PnL: {e}. Defaulting to 0.")
            return Decimal("0")

    # ---------- Marking ----------

    def _mark_price(
        self,
        fills_subset: List[Fill],
        market_id: str,
        asset_id: str,
        *,
        is_end_dt: bool = True,
    ) -> Decimal:
        m = self._get_market(market_id)
        is_resolved = asyncio.run(self.data.is_market_resolved(market_id))
        if m and (market_has_ended(m) or is_resolved):
            try:
                winning = self._is_asset_winning(m, asset_id)
                return Decimal("1") if winning else Decimal("0")
            except Exception:
                pass

        if is_end_dt:
            mid_price = self.clob.get_mid_from_book(asset_id)
            return Decimal(mid_price if mid_price else "0")

        # Fall back to last traded price for this asset from the subset
        for f in reversed(fills_subset):
            if f.asset_id == asset_id:
                return f.price

        return Decimal("0")

    # ---------- FIFO / Layers ----------

    @staticmethod
    def _fifo_accumulate(fills: List[Fill]) -> Tuple[Decimal, Dict[str, List[Tuple[Decimal, Decimal]]]]:
        realized = Decimal("0")
        inv_layers: Dict[str, List[Tuple[Decimal, Decimal]]] = {}
        for f in fills:
            aid = f.asset_id
            inv_layers.setdefault(aid, [])
            qty, price, fee = f.size, f.price, f.fee
            if f.side == "BUY":
                total_cost = (price * qty) + fee
                unit_cost = total_cost / qty if qty > 0 else Decimal("0")
                inv_layers[aid].append((qty, unit_cost))
            else:  # SELL
                remaining, sell_value, buy_cost_value = qty, Decimal("0"), Decimal("0")
                while remaining > 0 and inv_layers[aid]:
                    layer_qty, layer_cost = inv_layers[aid][0]
                    take = min(layer_qty, remaining)
                    buy_cost_value += take * layer_cost
                    sell_value += take * price
                    if take == layer_qty:
                        inv_layers[aid].pop(0)
                    else:
                        inv_layers[aid][0] = (layer_qty - take, layer_cost)
                    remaining -= take
                realized += (sell_value - buy_cost_value) - fee
        return realized, inv_layers

    @staticmethod
    def _layers_to_qty_avgcost(inv_layers: Dict[str, List[Tuple[Decimal, Decimal]]]) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        qty: Dict[str, Decimal] = {}
        avg: Dict[str, Decimal] = {}
        for aid, layers in inv_layers.items():
            if layers:
                total_q = sum(q for q, _ in layers)
                total_cost = sum(q * c for q, c in layers)
                qty[aid] = total_q
                avg[aid] = (total_cost / total_q) if total_q > 0 else Decimal("0")
            else:
                qty[aid] = Decimal("0")
                avg[aid] = Decimal("0")
        return qty, avg

    # ---------- Report ----------

    def generate_report(self, *, hours_back: int) -> str:
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(hours=hours_back)
        end_dt = now
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        realized_from_settlement = self._fetch_closed_pnl(start_ts, end_ts)

        fills_to_start = self._fetch_all_fills_upto(start_ts)
        fills_to_end = self._fetch_all_fills_upto(end_ts)

        fifo_realized_start, layers_start = self._fifo_accumulate(fills_to_start)
        fifo_realized_end, layers_end = self._fifo_accumulate(fills_to_end)
        fifo_realized_period = fifo_realized_end - fifo_realized_start

        realized_period = fifo_realized_period + realized_from_settlement

        inv_qty_start, avg_cost_start = self._layers_to_qty_avgcost(layers_start)
        inv_qty_end, avg_cost_end = self._layers_to_qty_avgcost(layers_end)

        def build_asset_market_map(fills: List[Fill]) -> Dict[str, str]:
            amap: Dict[str, str] = {}
            for f in fills:
                amap[f.asset_id] = f.market_id
            return amap

        amap_start = build_asset_market_map(fills_to_start)
        amap_end = build_asset_market_map(fills_to_end)

        # Unrealized PnL at START
        unrealized_start = Decimal("0")
        start_assets = [aid for aid, q in inv_qty_start.items() if q > 0]
        marks_start: Dict[str, Decimal] = {
            aid: self._mark_price(fills_to_start, amap_start[aid], aid, is_end_dt=False)
            for aid in start_assets
        }
        for aid, qty in inv_qty_start.items():
            if qty > 0:
                mark = marks_start.get(aid, Decimal("0"))
                unrealized_start += qty * (mark - avg_cost_start.get(aid, Decimal("0")))

        # Unrealized PnL at END
        unrealized_end = Decimal("0")
        end_assets = [aid for aid, q in inv_qty_end.items() if q > 0]
        marks_end: Dict[str, Decimal] = {
            aid: self._mark_price(fills_to_end, amap_end[aid], aid, is_end_dt=True)
            for aid in end_assets
        }
        for aid, qty in inv_qty_end.items():
            if qty > 0:
                mark = marks_end.get(aid, Decimal("0"))
                unrealized_end += qty * (mark - avg_cost_end.get(aid, Decimal("0")))

        unrealized_period = unrealized_end - unrealized_start
        total = realized_period + unrealized_period

        return (
            f"📊 <b>Performance Report</b>\n"
            f"🕒 <b>Time Window:</b> {start_dt:%Y-%m-%d %H:%M} → {end_dt:%Y-%m-%d %H:%M}\n"
            f"⏱ <b>Report Period:</b> {hours_back}h\n\n"
            f"💰 <b>Realized PnL (Trading FIFO):</b> {q2(fifo_realized_period)} USDC\n"
            f"💸 <b>Realized PnL (Settlements):</b> {q2(realized_from_settlement)} USDC\n"
            f"📈 <b>Total Realized PnL:</b> {q2(realized_period)} USDC\n\n"
            f"📊 <b>Unrealized PnL (Paper Value Change):</b> {q2(unrealized_period)} USDC\n"
            f"💹 <b>Total PnL for Period:</b> <code>{q2(total)} USDC</code>\n\n"
            f"📦 <b>Active Positions:</b> {len(end_assets)}\n"
            f"📄 <b>Fills Analyzed:</b> {len(fills_to_end)}"
        )


if __name__ == "__main__":
    svc = ReportService()
    print(svc.generate_report(hours_back=48))
