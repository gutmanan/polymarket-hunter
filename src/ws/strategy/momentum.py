from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Any, Deque, Optional, Tuple
from collections import deque

import pandas as pd
import pandas_ta as ta


class MomentumSignal(Enum):
    BULLISH = auto()
    BEARISH = auto()
    NEUTRAL = auto()


@dataclass
class DetectorConfig:
    # Buffering / warmup
    max_points: int = 1200          # rolling event window
    min_points: int = 30            # earliest we’ll attempt a real score
    warmup_points: int = 40         # after this, we enforce quality gates

    # Indicators
    rsi_len: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    pressure_lookback: int = 120    # events for net BUY-SELL
    microtrend_window: int = 20     # events for monotonic/microtrend checks

    # Quality gates
    spread_pct_max: float = 0.015   # ignore strong signals if spread too wide
    vol_window: int = 60            # rolling std window for mid returns
    vol_min_periods: int = 20
    vol_min_quantile: float = 0.20  # require volatility above this quantile

    # Scoring thresholds
    bullish_thresh: int = 3
    bearish_thresh: int = -3

    # Book parsing behaviors
    use_price_as_top_hint: bool = True   # if best_* are missing/flat, use `price` by side
    pressure_tiebreak_with_mid: bool = True  # if pressure ~0 but mid moved, sign pressure by mid delta

    # NaN handling / early behavior
    rsi_flat_fill: float = 50.0      # if series flat during warmup, fill RSI with this
    min_pressure_periods: int = 5
    min_vol_periods_start: int = 5   # early min periods so vol isn’t always 0
    macd_half_lengths_on_warmup: bool = True


class OrderbookMomentumDetector:
    """
    Accumulates Polymarket price_change events (best_bid/best_ask/price/size/side)
    and produces a bullish/bearish/neutral momentum label with strong confirmation.
    """

    def __init__(self, config: DetectorConfig = DetectorConfig()):
        self.cfg = config
        self.buf: Deque[Dict[str, Any]] = deque(maxlen=self.cfg.max_points)
        self._last_bid: Optional[float] = None
        self._last_ask: Optional[float] = None

    # ---------- Public API ----------
    def push_event(self, evt: Dict[str, Any]) -> None:
        """
        Ingest a Polymarket price_change event:
        {
          "price_changes": [
              {"best_bid": "...", "best_ask": "...", "price": "...", "size": "...", "side": "BUY"/"SELL"},
              ...
          ],
          ...
        }
        """
        pcs = evt.get("price_changes", [])
        if not pcs:
            return

        best_bid = self._last_bid
        best_ask = self._last_ask
        batch_pressure = 0.0

        for pc in pcs:
            side = str(pc.get("side") or "").upper()

            # Parse numeric fields
            bb = _to_float(pc.get("best_bid"))
            ba = _to_float(pc.get("best_ask"))
            px = _to_float(pc.get("price"))
            sz = _to_float(pc.get("size")) or 0.0

            # Update sides we actually got; keep the other side from last snapshot
            if bb is not None:
                best_bid = bb if best_bid is None else max(best_bid, bb)
            if ba is not None:
                best_ask = ba if best_ask is None else min(best_ask, ba)

            # Optional: use `price` as a hint when best_* are missing or equal
            if self.cfg.use_price_as_top_hint and px is not None:
                if side == "BUY":
                    if best_bid is None or px > best_bid:
                        best_bid = px
                elif side == "SELL":
                    if best_ask is None or px < best_ask:
                        best_ask = px

            # Signed order-flow pressure (BUY positive, SELL negative)
            if side == "BUY":
                batch_pressure += sz
            elif side == "SELL":
                batch_pressure -= sz

        # Require both sides eventually; if still missing, we can’t form a mid
        if best_bid is None or best_ask is None:
            return

        # Guard against zero/negative spread (crossed book)
        if best_ask <= best_bid:
            best_ask = best_bid + 1e-6

        # Compute features for this snapshot
        mid_prev = self.buf[-1]["mid"] if self.buf else None
        mid = 0.5 * (best_bid + best_ask)
        spread = best_ask - best_bid
        spread_pct = spread / mid if mid > 0 else math.inf

        # If pressure nets to ~0 but price clearly moved, use mid delta as tie-break
        if self.cfg.pressure_tiebreak_with_mid and abs(batch_pressure) < 1e-12 and mid_prev is not None and mid != mid_prev:
            batch_pressure = 1.0 if mid > mid_prev else -1.0

        # Persist last snapshot
        self._last_bid, self._last_ask = best_bid, best_ask

        self.buf.append({
            "ts": pd.Timestamp.utcnow(),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": mid,
            "spread": spread,
            "spread_pct": spread_pct,
            "pressure": batch_pressure
        })

    def get_signal(self) -> MomentumSignal:
        """Return just the discrete momentum label."""
        sig, _ = self.get_signal_with_debug()
        return sig

    def get_signal_with_debug(self) -> Tuple[MomentumSignal, Dict[str, Any]]:
        """
        Return (label, debug_dict) where debug_dict contains the latest features and score parts.
        """
        df = self._to_df()
        if len(df) < self.cfg.min_points:
            return MomentumSignal.NEUTRAL, {"reason": "warmup", "points": len(df)}

        ind = self._compute_indicators(df)
        row = ind.iloc[-1]
        warm = len(ind) >= self.cfg.warmup_points

        # Quality gates (only enforced after warmup)
        if warm:
            tight_spread = (row["spread_pct"] <= self.cfg.spread_pct_max)
            vol_floor = ind["vol"].quantile(self.cfg.vol_min_quantile) if ind["vol"].notna().any() else 0.0
            vol_ok = pd.notna(row["vol"]) and (row["vol"] >= (vol_floor or 0.0))
        else:
            tight_spread, vol_ok, vol_floor = True, True, 0.0

        score, parts = self._score_row(row)

        if warm and not (tight_spread and vol_ok):
            # dampen confidence; don’t overreact in poor market quality
            score = max(min(score, 1), -1)
            parts["quality_dampened"] = True
        else:
            parts["quality_dampened"] = False

        parts.update({
            "spread_pct": float(row["spread_pct"]),
            "vol": float(row.get("vol") or 0.0),
            "vol_floor": float(vol_floor or 0.0),
            "rsi": _to_float(row.get("rsi")),
            "macd_hist": _to_float(row.get("macd_hist")),
            "pressure_roll": _to_float(row.get("pressure_roll")),
            "points": len(ind),
            "score": int(score),
            "warm": warm
        })

        if score >= self.cfg.bullish_thresh:
            return MomentumSignal.BULLISH, parts
        if score <= self.cfg.bearish_thresh:
            return MomentumSignal.BEARISH, parts
        return MomentumSignal.NEUTRAL, parts

    def latest_features(self) -> pd.Series:
        """Convenience accessor to the latest computed features."""
        df = self._to_df()
        if df.empty:
            return pd.Series(dtype=float)
        ind = self._compute_indicators(df)
        return ind.iloc[-1]

    def reset(self) -> None:
        """Clear buffer and internal last bid/ask."""
        self.buf.clear()
        self._last_bid = None
        self._last_ask = None

    # ---------- Internals ----------
    def _to_df(self) -> pd.DataFrame:
        if not self.buf:
            return pd.DataFrame()
        df = pd.DataFrame(self.buf)
        return df.set_index("ts")

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        out = df.copy()

        # Returns & vol
        out["mid_ret"] = out["mid"].pct_change()
        # Early min_periods so vol kicks in before full window
        vol_min = cfg.min_vol_periods_start if len(out) < cfg.warmup_points else cfg.vol_min_periods
        out["vol"] = out["mid_ret"].rolling(cfg.vol_window, min_periods=vol_min).std()

        # RSI on mid; fill flat/early with neutral 50
        rsi_len = cfg.rsi_len if len(out) >= cfg.warmup_points else max(7, cfg.rsi_len // 2)
        rsi = ta.rsi(out["mid"], length=rsi_len)
        out["rsi"] = rsi.fillna(cfg.rsi_flat_fill)

        # MACD histogram (shorter during warmup to avoid long NaN period)
        if cfg.macd_half_lengths_on_warmup and len(out) < cfg.warmup_points:
            fast = max(6, cfg.macd_fast // 2)
            slow = max(13, cfg.macd_slow // 2)
            signal = max(5, cfg.macd_signal // 2)
        else:
            fast, slow, signal = cfg.macd_fast, cfg.macd_slow, cfg.macd_signal

        macd = ta.macd(out["mid"], fast=fast, slow=slow, signal=signal)
        if macd is not None and not macd.empty:
            # pandas_ta standard naming: MACD_..., MACDh_..., MACDs_...
            out["macd_hist"] = macd.iloc[:, 2].astype(float)
        else:
            out["macd_hist"] = 0.0

        # Pressure roll (BUY size - SELL size across recent events)
        lookback = min(cfg.pressure_lookback, max(cfg.min_pressure_periods, len(out)))
        out["pressure_roll"] = out["pressure"].rolling(lookback, min_periods=cfg.min_pressure_periods).sum()

        # Micro “trend” heuristic on mid
        win = min(cfg.microtrend_window, max(5, len(out) // 4))
        if win >= 5:
            seg = out["mid"].tail(win)
            inc5 = (seg.diff().tail(5) > 0).sum()
            dec5 = (seg.diff().tail(5) < 0).sum()
            out["micro_up"] = 1 if (seg.is_monotonic_increasing or inc5 >= 4) else 0
            out["micro_dn"] = 1 if (seg.is_monotonic_decreasing or dec5 >= 4) else 0
        else:
            out["micro_up"] = 0
            out["micro_dn"] = 0

        return out

    def _score_row(self, row: pd.Series) -> Tuple[int, Dict[str, int]]:
        """Return (score, parts) where parts shows contribution of each component."""
        parts: Dict[str, int] = {}
        score = 0

        # RSI
        rsi = _to_float(row.get("rsi"))
        if rsi is not None:
            if rsi >= 55:
                score += 1; parts["rsi"] = +1
            elif rsi <= 45:
                score -= 1; parts["rsi"] = -1
            else:
                parts["rsi"] = 0

        # MACD histogram
        mh = _to_float(row.get("macd_hist"))
        if mh is not None:
            if mh > 0:
                score += 1; parts["macd_hist"] = +1
            elif mh < 0:
                score -= 1; parts["macd_hist"] = -1
            else:
                parts["macd_hist"] = 0

        # Order-flow pressure
        pr = _to_float(row.get("pressure_roll"))
        if pr is not None:
            if pr > 0:
                score += 1; parts["pressure"] = +1
            elif pr < 0:
                score -= 1; parts["pressure"] = -1
            else:
                parts["pressure"] = 0

        # Micro trend
        mu = int(row.get("micro_up") or 0)
        md = int(row.get("micro_dn") or 0)
        if mu and not md:
            score += 1; parts["microtrend"] = +1
        elif md and not mu:
            score -= 1; parts["microtrend"] = -1
        else:
            parts["microtrend"] = 0

        return score, parts


# ---------- helpers ----------
def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None
