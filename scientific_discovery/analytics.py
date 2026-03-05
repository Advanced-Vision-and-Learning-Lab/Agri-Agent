from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


def _mad(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    med = np.median(x)
    return float(np.median(np.abs(x - med)))


def robust_zscore(x: np.ndarray) -> np.ndarray:
    x = x.astype(float)
    med = np.nanmedian(x)
    mad = _mad(x)
    if not np.isfinite(mad) or mad == 0:
        return np.full_like(x, np.nan, dtype=float)
    return 0.6745 * (x - med) / mad


def rolling_smooth(series: pd.Series, window: int = 3) -> pd.Series:
    if window <= 1:
        return series
    return series.rolling(window=window, center=True, min_periods=1).median()


@dataclass(frozen=True)
class ChangePoint:
    idx: int
    date: str
    kind: str  # "rise" or "drop"
    magnitude: float
    z: float
    column: str


def detect_changepoints(
    df: pd.DataFrame,
    column: str,
    *,
    smooth_window: int = 3,
    z_thresh: float = 3.5,
) -> List[ChangePoint]:
    """
    Lightweight change-point detector without extra dependencies.
    Uses robust z-score on first differences of a smoothed series.
    """
    if column not in df.columns or df.empty:
        return []

    s = pd.to_numeric(df[column], errors="coerce")
    s_sm = rolling_smooth(s, window=smooth_window)
    dif = s_sm.diff().to_numpy(dtype=float)
    z = robust_zscore(dif)

    cps: List[ChangePoint] = []
    for i in range(1, len(dif)):
        if not np.isfinite(z[i]):
            continue
        if abs(z[i]) < z_thresh:
            continue
        kind = "rise" if dif[i] > 0 else "drop"
        dt = str(df.loc[i, "date"].date()) if "date" in df.columns and pd.notna(df.loc[i, "date"]) else str(i)
        cps.append(
            ChangePoint(
                idx=int(i),
                date=dt,
                kind=kind,
                magnitude=float(dif[i]),
                z=float(z[i]),
                column=column,
            )
        )
    return cps


def slope_per_day(df: pd.DataFrame, column: str) -> pd.Series:
    """Compute discrete slope per day between timepoints."""
    if column not in df.columns or "date" not in df.columns:
        return pd.Series([np.nan] * len(df))
    x = pd.to_numeric(df[column], errors="coerce")
    t = pd.to_datetime(df["date"])
    dt_days = t.diff().dt.total_seconds() / 86400.0
    dx = x.diff()
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = dx / dt_days
    return slope


@dataclass(frozen=True)
class LagResult:
    lag_days: int
    corr: float
    n: int


def _to_daily_grid(dates: pd.Series, values: pd.Series) -> Tuple[np.ndarray, np.ndarray]:
    t = pd.to_datetime(dates)
    v = pd.to_numeric(values, errors="coerce").astype(float)
    mask = t.notna() & v.notna()
    t = t[mask]
    v = v[mask]
    if len(t) < 3:
        return np.array([]), np.array([])

    t0 = t.min()
    days = (t - t0).dt.total_seconds().to_numpy(dtype=float) / 86400.0
    v_arr = v.to_numpy(dtype=float)
    grid = np.arange(int(np.floor(days.min())), int(np.ceil(days.max())) + 1, 1, dtype=float)
    if grid.size < 3:
        return np.array([]), np.array([])

    v_grid = np.interp(grid, days, v_arr)
    return grid, v_grid


def lag_search_corr(
    df: pd.DataFrame,
    lead_col: str,
    response_col: str,
    *,
    response_use_slope: bool = True,
    lag_min: int = -10,
    lag_max: int = 10,
) -> List[LagResult]:
    """
    Compute correlation for lead/lag relationships on a daily interpolated grid.
    Convention: lag_days > 0 means lead_col leads response_col by lag_days.
    """
    if "date" not in df.columns or lead_col not in df.columns or response_col not in df.columns:
        return []

    lead = pd.to_numeric(df[lead_col], errors="coerce")
    response = pd.to_numeric(df[response_col], errors="coerce")
    if response_use_slope:
        response = slope_per_day(df.assign(**{response_col: response}), response_col)

    g1, x = _to_daily_grid(df["date"], lead)
    g2, y = _to_daily_grid(df["date"], response)
    if g1.size == 0 or g2.size == 0:
        return []

    start = max(g1.min(), g2.min())
    end = min(g1.max(), g2.max())
    grid = np.arange(start, end + 1, 1, dtype=float)
    if grid.size < 5:
        return []

    xg = np.interp(grid, g1, x)
    yg = np.interp(grid, g2, y)

    out: List[LagResult] = []
    for lag in range(int(lag_min), int(lag_max) + 1):
        if lag == 0:
            xa, ya = xg, yg
        elif lag > 0:
            xa, ya = xg[:-lag], yg[lag:]
        else:
            k = -lag
            xa, ya = xg[k:], yg[:-k]

        mask = np.isfinite(xa) & np.isfinite(ya)
        n = int(mask.sum())
        if n < 5:
            continue
        xv = xa[mask]
        yv = ya[mask]
        if np.std(xv) == 0 or np.std(yv) == 0:
            continue
        corr = float(np.corrcoef(xv, yv)[0, 1])
        out.append(LagResult(lag_days=int(lag), corr=corr, n=n))

    out.sort(key=lambda r: abs(r.corr), reverse=True)
    return out


def qc_flags(df: pd.DataFrame) -> List[Dict]:
    """Basic QC for single-plant timeseries. Flags suspicious segmentation/extraction points."""
    flags: List[Dict] = []
    if df.empty:
        return flags

    if "mask_area_pixels" in df.columns:
        area = pd.to_numeric(df["mask_area_pixels"], errors="coerce").astype(float)
        for i in range(len(area)):
            if not np.isfinite(area.iloc[i]):
                continue
            if area.iloc[i] < 500:
                flags.append({"idx": int(i), "date": str(df.loc[i, "date"].date()), "type": "mask_too_small", "value": float(area.iloc[i])})
        ratio = area / area.shift(1)
        for i in range(1, len(ratio)):
            r = ratio.iloc[i]
            if not np.isfinite(r):
                continue
            if r > 2.0 or r < 0.5:
                flags.append(
                    {
                        "idx": int(i),
                        "date": str(df.loc[i, "date"].date()),
                        "type": "mask_area_jump",
                        "ratio_vs_prev": float(r),
                        "prev": float(area.iloc[i - 1]) if np.isfinite(area.iloc[i - 1]) else None,
                        "curr": float(area.iloc[i]),
                    }
                )

    return flags
