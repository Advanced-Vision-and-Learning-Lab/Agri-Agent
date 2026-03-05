from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .agent_lab import run_multi_agent_lab
from .analytics import detect_changepoints, lag_search_corr, qc_flags
from .evidence import build_evidence_table, pick_signals
from .io import load_all
from .render import write_discovery_markdown, write_json


def _as_event_dict(cp) -> Dict[str, Any]:
    return {
        "idx": cp.idx,
        "date": cp.date,
        "column": cp.column,
        "kind": cp.kind,
        "magnitude": cp.magnitude,
        "z": cp.z,
    }


def _signal_timeseries(df: pd.DataFrame, signals_used: Dict[str, str]) -> List[Dict[str, Any]]:
    cols = ["date", "mask_area_pixels"] + list(signals_used.values())
    cols = [c for c in cols if c in df.columns]
    out: List[Dict[str, Any]] = []
    for _, row in df[cols].iterrows():
        d: Dict[str, Any] = {}
        dt = row.get("date")
        try:
            d["date"] = str(pd.to_datetime(dt).date())
        except Exception:
            d["date"] = str(dt)
        for k in ["mask_area_pixels"]:
            if k in row.index:
                v = row.get(k)
                d[k] = None if pd.isna(v) else float(v)
        for friendly, col in signals_used.items():
            v = row.get(col)
            d[friendly] = None if pd.isna(v) else float(v)
        out.append(d)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Agentic scientific discovery over pipeline results.json time-series")
    ap.add_argument("--results-dir", type=Path, required=True, help="Root directory containing per-date results.json files")
    ap.add_argument("--out-dir", type=Path, required=True, help="Output directory for discovery artifacts")
    ap.add_argument("--smooth-window", type=int, default=3, help="Rolling median window for change-point detection")
    ap.add_argument("--z-thresh", type=float, default=3.5, help="Robust z-score threshold on first differences")
    ap.add_argument("--lag-min", type=int, default=-10, help="Minimum lag (days) to test")
    ap.add_argument("--lag-max", type=int, default=10, help="Maximum lag (days) to test")
    ap.add_argument("--no-llm", action="store_true", help="Disable LLM calls even if LLM_API_KEY is set")
    ap.add_argument(
        "--save-transcript",
        action="store_true",
        help="Write agent prompts/responses to out_dir/agent_transcript.jsonl (no API keys).",
    )
    args = ap.parse_args(argv)

    records = load_all(args.results_dir)
    table = build_evidence_table(records)
    df = table.df.copy()

    if df.empty:
        raise SystemExit("No records loaded.")

    picked = pick_signals(df)
    signals_used = {k: v for k, v in picked.items() if v is not None}

    qc = qc_flags(df)

    cps: List[Dict[str, Any]] = []
    for friendly, col in signals_used.items():
        for cp in detect_changepoints(df, col, smooth_window=args.smooth_window, z_thresh=args.z_thresh):
            cps.append(_as_event_dict(cp))
    cps.sort(key=lambda x: abs(float(x.get("z", 0.0))), reverse=True)

    lag_relationships: List[Dict[str, Any]] = []
    lead_candidates = []
    if picked.get("veg_NDRE_mean"):
        lead_candidates.append(("NDRE_mean", picked["veg_NDRE_mean"]))
    if picked.get("veg_NDVI_mean"):
        lead_candidates.append(("NDVI_mean", picked["veg_NDVI_mean"]))

    response_candidates = []
    if picked.get("morph_height_cm"):
        response_candidates.append(("height_cm", picked["morph_height_cm"]))
    if picked.get("morph_area_cm2"):
        response_candidates.append(("area_cm2", picked["morph_area_cm2"]))
    if picked.get("morph_skeleton_cm"):
        response_candidates.append(("skeleton_cm", picked["morph_skeleton_cm"]))

    for lead_name, lead_col in lead_candidates:
        for resp_name, resp_col in response_candidates:
            lags = lag_search_corr(
                df,
                lead_col=lead_col,
                response_col=resp_col,
                response_use_slope=True,
                lag_min=args.lag_min,
                lag_max=args.lag_max,
            )
            if lags:
                best = lags[0]
                lag_relationships.append(
                    {
                        "lead_signal": lead_name,
                        "response_signal": f"d/dt {resp_name}",
                        "lag_days": best.lag_days,
                        "corr": best.corr,
                        "n": best.n,
                    }
                )
    lag_relationships.sort(key=lambda x: abs(float(x.get("corr", 0.0))), reverse=True)

    evidence = {
        "signals_used": signals_used,
        "n_timepoints": int(len(df)),
        "dates": [str(d.date()) for d in pd.to_datetime(df["date"]).tolist()],
        "signal_timeseries": _signal_timeseries(df, signals_used),
        "qc_flags": qc,
        "changepoints": cps[:20],
        "lag_relationships": lag_relationships[:20],
    }

    transcript: Optional[List[Dict[str, Any]]] = [] if args.save_transcript else None
    agent_lab = run_multi_agent_lab(evidence, use_llm_if_available=not args.no_llm, transcript=transcript)

    date_range = f"{df['date'].min().date()} → {df['date'].max().date()}"
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence_csv = out_dir / "evidence_timeseries.csv"
    df.to_csv(evidence_csv, index=False)

    transcript_path: Optional[Path] = None
    if transcript is not None:
        transcript_path = out_dir / "agent_transcript.jsonl"
        with open(transcript_path, "w", encoding="utf-8") as f:
            for entry in transcript:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    report: Dict[str, Any] = {
        "summary": {
            "n_timepoints": int(len(df)),
            "date_range": date_range,
            "signals_used": list(signals_used.keys()),
            "results_dir": str(args.results_dir),
        },
        "evidence_overview": {
            "evidence_timeseries_csv": str(evidence_csv),
            **({"agent_transcript_jsonl": str(transcript_path)} if transcript_path else {}),
        },
        "qc_flags": qc,
        "changepoints": cps[:50],
        "lag_relationships": lag_relationships[:50],
        "agent_lab": agent_lab,
        "next_steps": [
            "If any QC flags exist, manually inspect overlay.png for those dates and consider re-running segmentation.",
            "Increase sampling density (more dates) to improve change-point and lag detection reliability.",
            "Add a robustness check: recompute lags after dropping one timepoint at a time.",
        ],
    }

    write_json(report, out_dir / "discovery_report.json")
    write_discovery_markdown(report, out_dir / "discovery_report.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
