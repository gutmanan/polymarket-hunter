# pip install filterpy numpy
import math
import time
from typing import Dict, Optional

import numpy as np
from filterpy.kalman import KalmanFilter

from polymarket_hunter.dal.datamodel.trend_prediction import TrendPrediction, Direction


class KalmanTrend:

    def __init__(
            self,
            use_logit: bool = True,
            q0: float = 1e-6,
            r_floor: float = 1e-5,
            max_dt: float = 1.0,
            t_enter: float = 2.0,   # need this to switch to UP/DOWN
            t_hold: float = 1.0,    # stay in current direction if |t|>=t_hold
            t_alpha: float = 0.3,   # EMA on t-stat to avoid flicker
            reset_z: float = 8.0,   # reset on huge innovation
            reset_inflate: float = 10.0,
    ):
        self.use_logit, self.q0, self.r_floor, self.max_dt = use_logit, q0, r_floor, max_dt
        self.t_enter, self.t_hold, self.t_alpha = float(t_enter), float(t_hold), float(t_alpha)
        self.reset_z, self.reset_inflate = float(reset_z), float(reset_inflate)

        self._kf: Dict[str, KalmanFilter] = {}
        self._ts: Dict[str, float] = {}
        self._t_ema: Dict[str, float] = {}
        self._dir: Dict[str, Direction] = {}

        # logit controls
        self._CLIP = 1e-3
        self._MAX_JAC = 30.0  # cap d(logit)/dp to tame 0.98..0.995 edges

    # ---------- helpers ----------
    def _clip01(self, p: float) -> float:
        return min(max(float(p), self._CLIP), 1.0 - self._CLIP)

    def _logit(self, p: float) -> float:
        p = self._clip01(p)
        return math.log(p / (1.0 - p))

    def _jac(self, p: float) -> float:
        p = self._clip01(p)
        j = 1.0 / (p * (1.0 - p))
        return j if j < self._MAX_JAC else self._MAX_JAC

    @staticmethod
    def _conf(t: float) -> float:
        a = abs(t)
        return a / (1.0 + a)  # smooth 0..1

    @staticmethod
    def _var_from_spread(spread: Optional[float]) -> float:
        if spread is None or not math.isfinite(spread) or spread <= 0:
            return 1e-5
        return (spread * 0.5) ** 2 + 1e-5  # add tiny base

    # ---------- Public API ----------
    def update(
            self,
            key: str,
            mid: float,
            spread: Optional[float],
            ts: Optional[float] = None,
            tick_size: Optional[float] = None
    ) -> TrendPrediction:
        ts = float(ts if ts is not None else time.time())
        p = self._clip01(mid)

        # measurement transform & jacobian
        if self.use_logit:
            z, jac = self._logit(p), self._jac(p)
        else:
            z, jac = p, 1.0

        # init
        if key not in self._kf:
            kf = KalmanFilter(dim_x=2, dim_z=1)
            kf.x = np.array([[z], [0.0]])  # [price, velocity]
            kf.F = np.array([[1.0, 1.0], [0.0, 1.0]])
            kf.H = np.array([[1.0, 0.0]])
            kf.P = np.array([[1e-3, 0.0], [0.0, 1e-2]])
            kf.Q = np.eye(2) * 1e-6
            kf.R = np.array([[1e-5]])
            self._kf[key], self._ts[key] = kf, ts
            self._t_ema[key] = 0.0
            self._dir[key] = Direction.FLAT
            return TrendPrediction(direction=Direction.FLAT, t_stat=0.0, velocity=0.0, confidence=0.0)

        # dt & models
        dt = max(0.0, min(self.max_dt, ts - self._ts[key])); self._ts[key] = ts
        kf = self._kf[key]
        kf.F[0, 1] = dt

        dt2, dt3 = dt * dt, dt * dt * dt
        kf.Q = np.array([[dt3 / 3.0, dt2 / 2.0], [dt2 / 2.0, dt]]) * self.q0

        # R from spread/tick/staleness; map to measurement space via jac^2
        var_p = self._var_from_spread(spread) * (1.0 + 2.0 * dt)  # staleness boost
        if tick_size and tick_size > 0:
            var_p = max(var_p, (tick_size ** 2) / 12.0)
        var_p = max(var_p, self.r_floor)
        kf.R[0, 0] = (jac * jac) * var_p

        # predict, reset-on-jump, update
        kf.predict()
        y, S = float(z - kf.x[0, 0]), float(kf.P[0, 0] + kf.R[0, 0])
        if abs(y) / max(1e-12, math.sqrt(S)) > self.reset_z:
            kf.P *= self.reset_inflate
        kf.update(np.array([[z]]))

        # velocity t-stat
        v = float(kf.x[1, 0]); vvar = float(max(kf.P[1, 1], 1e-12))
        raw_t = v / math.sqrt(vvar)

        # tiny EMA + hysteresis -> stable direction
        t_prev = self._t_ema.get(key, raw_t)
        t = t_prev + self.t_alpha * (raw_t - t_prev)
        self._t_ema[key] = t

        d: Direction = Direction.FLAT
        if t >= self.t_enter or (t >= self.t_hold and self._dir.get(key) == Direction.UP):
            d = Direction.UP
        elif t <= -self.t_enter or (t <= -self.t_hold and self._dir.get(key) == Direction.DOWN):
            d = Direction.DOWN
        self._dir[key] = d if d != Direction.FLAT else self._dir.get(key, Direction.FLAT)

        return TrendPrediction(direction=d, t_stat=t, velocity=v, confidence=self._conf(t))
