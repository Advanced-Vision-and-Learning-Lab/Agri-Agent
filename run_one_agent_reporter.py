#!/usr/bin/env python3
"""
Run ONE LLM agent (Reporter) on phenotyping results and write a single output JSON.

Inputs:
  - results_dir/**/results.json (e.g. SorghumO_over_time_results/SorghumO_over_time/)

Env (OpenAI-compatible):
  - LLM_API_KEY (required for LLM)
  - LLM_API_BASE (default: https://api.openai.com/v1)
  - LLM_MODEL (default: gpt-4o-mini)

Outputs:
  - out_dir/one_agent_reporter.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scientific_discovery.agent_lab import REPORTER_AGENT, run_agent_fallback, run_agent_llm
from scientific_discovery.analytics import detect_changepoints, lag_search_corr, qc_flags
from scientific_discovery.evidence import build_evidence_table, pick_signals
from scientific_discovery.io import load_all


def _pick_minimal_signals(picked: dict[str, str | None]) -> dict[str, str]:
    """Keep the LLM input small: 3 signals (1 morphology, 1 vegetation index, 1 texture)."""
    out: dict[str, str] = {}

    for k in ["morph_height_cm", "morph_area_cm2", "morph_skeleton_cm"]:
        if picked.get(k):
            out[k] = str(picked[k])
            break

    for k in ["veg_NDRE_mean", "veg_NDVI_mean"]:
        if picked.get(k):
            out[k] = str(picked[k])
            break

    for k in ["tex_lac1_mean", "tex_ehd_mean"]:
        if picked.get(k):
            out[k] = str(picked[k])
            break

    return out


def _signal_timeseries(df: pd.DataFrame, signals_used: dict[str, str]) -> list[dict]:
    cols = ["date", "mask_area_pixels"] + list(signals_used.values())
    cols = [c for c in cols if c in df.columns]
    out: list[dict] = []
    for _, row in df[cols].iterrows():
        d: dict = {}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run ONE Reporter LLM agent and write one JSON output")
    ap.add_argument("--results-dir", type=Path, default=None, help="Results directory (default: SorghumO_over_time_results/SorghumO_over_time)")
    ap.add_argument("--out-dir", type=Path, default=None, help="Output directory (default: SorghumO_over_time_discovery)")
    ap.add_argument("--require-llm", action="store_true", help="Fail if LLM call does not succeed (no fallback output).")
    ap.add_argument("--max-timepoints", type=int, default=14, help="Limit dates passed to the LLM (keeps prompts small).")
    ap.add_argument("--full-signals", action="store_true", help="Use all auto-picked signals instead of the minimal 3-signal set.")
    ap.add_argument(
        "--save-transcript",
        action="store_true",
        help="Write agent prompt/response to out_dir/agent_transcript.jsonl (no API keys).",
    )
    args = ap.parse_args(argv)

    base = Path(__file__).parent
    results_dir = args.results_dir or (base / "SorghumO_over_time_results" / "SorghumO_over_time")
    out_dir = args.out_dir or (base / "SorghumO_over_time_discovery")
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_all(results_dir)
    table = build_evidence_table(records)
    df = table.df.copy()

    picked = pick_signals(df)
    if args.full_signals:
        signals_used = {k: v for k, v in picked.items() if v is not None}
    else:
        signals_used = _pick_minimal_signals(picked)
    if not signals_used:
        raise SystemExit("No usable signals found in evidence table.")

    qc = qc_flags(df)

    if args.max_timepoints and args.max_timepoints > 0 and len(df) > args.max_timepoints:
        df = df.tail(args.max_timepoints).reset_index(drop=True)

    cps = []
    for _, col in signals_used.items():
        for cp in detect_changepoints(df, col):
            cps.append(
                {
                    "idx": cp.idx,
                    "date": cp.date,
                    "column": cp.column,
                    "kind": cp.kind,
                    "magnitude": cp.magnitude,
                    "z": cp.z,
                }
            )
    cps.sort(key=lambda x: abs(float(x.get("z", 0.0))), reverse=True)

    lag_relationships = []
    lead_col = signals_used.get("veg_NDVI_mean") or signals_used.get("veg_NDRE_mean")
    resp_col = signals_used.get("morph_height_cm") or signals_used.get("morph_area_cm2") or signals_used.get("morph_skeleton_cm")
    if lead_col and resp_col:
        lags = lag_search_corr(df, lead_col=lead_col, response_col=resp_col)
        if lags:
            best = lags[0]
            lag_relationships.append(
                {"lead_col": lead_col, "response_col": resp_col, "lag_days": best.lag_days, "corr": best.corr, "n": best.n}
            )

    evidence = {
        "signals_used": signals_used,
        "n_timepoints": int(len(df)),
        "signal_timeseries": _signal_timeseries(df, signals_used),
        "qc_flags": qc,
        "changepoints": cps[:8],
        "lag_relationships": lag_relationships,
        "task": "Write ONE conservative discovery summary (1–3 bullets) backed by the evidence. Use only the evidence fields; do not guess causes.",
    }

    transcript = [] if args.save_transcript else None
    try:
        out = run_agent_llm(REPORTER_AGENT, evidence, round_label="single_agent", transcript=transcript)
        out["llm_used"] = True
    except Exception as e:
        if args.require_llm:
            raise SystemExit(f"LLM call failed (and --require-llm set): {type(e).__name__}: {e}")
        out = run_agent_fallback(REPORTER_AGENT, evidence, round_label="single_agent")
        out["llm_used"] = False
        out["error"] = f"LLM failed: {type(e).__name__}: {e}"

    out_path = out_dir / "one_agent_reporter.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    if transcript is not None:
        tpath = out_dir / "agent_transcript.jsonl"
        tpath.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in transcript) + "\n", encoding="utf-8")
    print(f"Wrote: {out_path}")
    print(json.dumps(out, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
