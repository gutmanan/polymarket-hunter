# src/ws/handler/price_change_handler.py
import json
from typing import Any, Dict, Optional

from src.ws.handler.handlers import MessageHandler, MessageContext

TARGET_SUM = 0.90          # buy both if best_ask_up + best_ask_down ≤ 0.90  (~10% edge)
SIZE_USD_BUDGET = 90.0     # max total USDC spend across BOTH legs at TARGET_SUM
MIN_SHARES = 5.0           # require at least this many shares per leg (avoid dust)
MAX_SHARES = 200.0         # cap each leg size (risk cap)
SPREAD_CAP = 0.02          # optional: skip if any leg's (ask-bid) > 2c

BUY_SIDE = 0               # py_clob_client convention: 0=BUY, 1=SELL

class PriceChangeHandler(MessageHandler):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg.get("event_type") == "price_change"

    # ---- tiny helpers -------------------------------------------------------

    def _pair_tokens(self, ctx: MessageContext, condition_id: str) -> Optional[tuple[str, str]]:
        m = ctx.markets.get(condition_id)
        if not m:
            return None
        try:
            ids = json.loads(m.get("clobTokenIds", "[]"))
            if len(ids) == 2:
                return (str(ids[0]), str(ids[1]))
        except Exception:
            pass
        return None

    def _extract_leg(self, price_changes: list[dict], token_id: str) -> Optional[dict]:
        for pc in price_changes:
            if pc.get("asset_id") == token_id:
                return pc
        return None

    def _safe_float(self, v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return default

    def _shares_from_budget(self, ask_sum: float) -> float:
        if ask_sum <= 0:
            return 0.0
        s = SIZE_USD_BUDGET / ask_sum
        return max(MIN_SHARES, min(MAX_SHARES, s))

    # ---- main ---------------------------------------------------------------

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        pcs = msg.get("price_changes") or []
        condition_id = msg.get("market")
        pair = self._pair_tokens(ctx, condition_id)
        if not pair:
            return

        t0, t1 = pair
        leg0 = self._extract_leg(pcs, t0)
        leg1 = self._extract_leg(pcs, t1)

        # If event didn’t carry both legs (can happen), bail — we only act when we see both asks together.
        if not (leg0 and leg1):
            return

        bid0 = self._safe_float(leg0.get("best_bid"))
        ask0 = self._safe_float(leg0.get("best_ask"))
        bid1 = self._safe_float(leg1.get("best_bid"))
        ask1 = self._safe_float(leg1.get("best_ask"))

        # Optional sanity: avoid super-wide legs
        if (ask0 - bid0) > SPREAD_CAP or (ask1 - bid1) > SPREAD_CAP:
            return

        ask_sum = ask0 + ask1
        if ask_sum > TARGET_SUM:
            return  # no edge

        # Compute equal-shares size so total spend ~ SIZE_USD_BUDGET
        shares = self._shares_from_budget(ask_sum)
        if shares < MIN_SHARES:
            return

        # Place LIMIT BUY on both legs at observed asks to cap slippage
        # Assumes your CLOBClient has execute_limit_order(token_id, price, size, side)
        # If you only have market, you lose the price cap—strongly prefer limit.
        try:
            oid0 = ctx.clob_client.execute_limit_order(token_id=t0, price=ask0, size=shares, side=BUY_SIDE)
        except Exception as e:
            ctx.logger.error(f"[ARBIT] leg0 limit failed {t0} @ {ask0}: {e}")
            return

        try:
            oid1 = ctx.clob_client.execute_limit_order(token_id=t1, price=ask1, size=shares, side=BUY_SIDE)
        except Exception as e:
            ctx.logger.error(f"[ARBIT] leg1 limit failed {t1} @ {ask1}: {e} — unwinding leg0")
            # Best-effort unwind leg0 if leg1 failed
            try:
                # Cancel first; if cancel API isn’t available or it already filled, dump with market.
                ctx.clob_client.cancel_order(oid0)
            except Exception:
                # If cancel not possible, dump via market (could lose a few bps)
                notional0 = shares * ask0
                try:
                    ctx.clob_client.execute_market_order(token_id=t0, amount=notional0)
                except Exception as e2:
                    ctx.logger.error(f"[ARBIT] unwind of leg0 failed: {e2}")
            return

        ctx.logger.info(f"[ARBIT] Bought both legs {t0}@{ask0:.3f} + {t1}@{ask1:.3f} | shares={shares:.2f} | sum={ask_sum:.3f}")

        # From here you’re delta-neutral; no need to manage TP/SL.
        # You can optionally add a tiny monitor to verify both orders filled
        # and re-buy small residuals if partial fills are common.
