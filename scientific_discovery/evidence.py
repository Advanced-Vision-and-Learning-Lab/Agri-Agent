from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .io import ResultRecord


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool)


def flatten_numeric(d: Any, prefix: str = "") -> Dict[str, float]:
    """
    Flatten nested dict/list structures into a 1D dict of numeric values only.
    """
    out: Dict[str, float] = {}

    if isinstance(d, dict):
        for k, v in d.items():
            k = str(k)
            key = f"{prefix}__{k}" if prefix else k
            out.update(flatten_numeric(v, key))
        return out

    if _is_number(d):
        if prefix:
            out[prefix] = float(d)
        return out

    if isinstance(d, (list, tuple)):
        if len(d) == 1 and _is_number(d[0]) and prefix:
            out[prefix] = float(d[0])
        return out

    return out


@dataclass(frozen=True)
class EvidenceTable:
    df: pd.DataFrame
    feature_columns: List[str]


def build_evidence_table(records: Iterable[ResultRecord]) -> EvidenceTable:
    rows: List[Dict[str, Any]] = []
    for r in records:
        base: Dict[str, Any] = {
            "date": r.date,
            "image_name": r.image_name,
            "image_path": r.image_path,
            "results_json": str(r.path),
            "num_instances_detected": r.raw.get("num_instances_detected"),
            "mask_area_pixels": r.raw.get("mask_area_pixels"),
        }

        veg = flatten_numeric(r.raw.get("vegetation_indices", {}), prefix="veg")
        tex = flatten_numeric(r.raw.get("texture_features", {}), prefix="tex")
        morph = flatten_numeric(r.raw.get("morphology_features", {}), prefix="morph")

        row = {**base, **veg, **tex, **morph}
        rows.append(row)

    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

    meta_cols = {"date", "image_name", "image_path", "results_json"}
    numeric_cols = []
    for c in df.columns:
        if c in meta_cols:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            numeric_cols.append(c)
        else:
            coerced = pd.to_numeric(df[c], errors="coerce")
            if coerced.notna().any():
                df[c] = coerced
                numeric_cols.append(c)

    return EvidenceTable(df=df, feature_columns=sorted(numeric_cols))


def pick_signals(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """
    Heuristic default signals for single-plant time-series discovery.
    Returns mapping from friendly-name -> column name.
    """
    candidates: List[Tuple[str, List[str]]] = [
        ("morph_area_cm2", ["morph__area_cm2", "morph__size_area"]),
        ("morph_height_cm", ["morph__height_cm", "morph__size_height"]),
        ("morph_skeleton_cm", ["morph__skeleton_length_cm", "morph__size_longest_path"]),
        ("veg_NDRE_mean", ["veg__NDRE__statistics__mean", "veg__LCI__statistics__mean"]),
        ("veg_NDVI_mean", ["veg__NDVI__statistics__mean", "veg__OSAVI__statistics__mean"]),
        ("tex_lac1_mean", ["tex__pca__statistics__lac1__mean", "tex__color__statistics__lac1__mean"]),
        ("tex_ehd_mean", ["tex__pca__statistics__ehd_map__mean", "tex__color__statistics__ehd_map__mean"]),
    ]

    picked: Dict[str, Optional[str]] = {}
    cols = set(df.columns)
    for friendly, options in candidates:
        picked[friendly] = next((c for c in options if c in cols), None)
    return picked
