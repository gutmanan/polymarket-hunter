import time
import pandas as pd
import pandas_ta as ta
from typing import Dict, Any, Optional
from src.ws.handler.handlers import MessageHandler, MessageContext


class PriceChangeHandler(MessageHandler):
    def __init__(self):
        self.fast_len = 12
        self.slow_len = 26
        self.band = 0.006  # 0.6% neutral band around slow EMA
        self.confirm_bars = 3  # require N consecutive confirmations
        self.cooldown_s = 10  # min seconds between signals per asset
        self.max_spread = 0.06  # ignore ticks if spread > 6 cents (prices ~0..1)
        self.hist_cap = 300

        self.price_history: Dict[str, list[float]] = {}
        self.state: Dict[str, Dict[str, Any]] = {}  # signal, streak, last_emit_ts

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg.get("event_type") == "price_change"

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        now = time.time()
        for pc in msg["price_changes"]:
            asset_id = pc["asset_id"]
            p = self._midprice(pc)
            if p is None:
                continue

            hist = self.price_history.setdefault(asset_id, [])
            hist.append(p)
            if len(hist) > self.hist_cap:
                self.price_history[asset_id] = hist = hist[-self.hist_cap:]

            # need enough data to compute both EMAs
            if len(hist) < max(self.fast_len, self.slow_len) + self.confirm_bars:
                continue

            s = pd.Series(hist)
            ema_fast = ta.ema(s, length=self.fast_len).iloc[-1]
            ema_slow = ta.ema(s, length=self.slow_len).iloc[-1]

            # hysteresis band around slow EMA to avoid flip-flops
            up_thresh = ema_slow * (1 + self.band)
            dn_thresh = ema_slow * (1 - self.band)

            raw_signal = 1 if ema_fast > up_thresh else (-1 if ema_fast < dn_thresh else 0)

            st = self.state.setdefault(asset_id, {"signal": 0, "streak": 0, "last_emit_ts": 0.0})

            # build confirmation streak only when raw_signal is directional
            if raw_signal == 0:
                # drift inside band → decay streak toward 0
                st["streak"] = max(0, st["streak"] - 1)
                continue

            # same direction as last raw tick → increase streak, else reset
            if (st["streak"] >= 0 and raw_signal == 1) or (st["streak"] <= 0 and raw_signal == -1):
                st["streak"] += raw_signal
            else:
                st["streak"] = raw_signal  # reset in the new direction

            # only emit when: (a) confirmed by streak, (b) actually changed vs last emitted, (c) cooldown passed
            confirmed = abs(st["streak"]) >= self.confirm_bars
            changed = raw_signal != st["signal"]
            cooled = (now - st["last_emit_ts"]) >= self.cooldown_s

            if confirmed and changed and cooled:
                direction = "📈 uptrend" if raw_signal == 1 else "📉 downtrend"
                ctx.logger.info(
                    f"{asset_id} {direction} | price={p:.4f} "
                    f"ema_fast={ema_fast:.4f} ema_slow={ema_slow:.4f} "
                    f"band={self.band:.3%} streak={st['streak']}"
                )
                st["signal"] = raw_signal
                st["last_emit_ts"] = now

    def _midprice(self, pc: Dict[str, Any]) -> Optional[float]:
        try:
            bb = float(pc.get("best_bid")) if pc.get("best_bid") is not None else None
            ba = float(pc.get("best_ask")) if pc.get("best_ask") is not None else None
            if bb is not None and ba is not None and bb > 0 and ba > 0:
                # optional spread filter to cut noisy prints
                if self.max_spread is not None and (ba - bb) > self.max_spread:
                    return None
                return 0.5 * (bb + ba)
            # fallback to trade price
            p = float(pc["price"])
            return p if p > 0 else None
        except Exception:
            return None
