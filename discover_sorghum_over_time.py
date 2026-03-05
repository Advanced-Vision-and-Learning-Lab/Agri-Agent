#!/usr/bin/env python3
"""
Run the full multi-agent discovery pipeline on phenotyping results.

Inputs:
  - results_dir: directory containing **/results.json (e.g. SorghumO_over_time_results/SorghumO_over_time/)

Outputs:
  - out_dir/discovery_report.json
  - out_dir/discovery_report.md
  - out_dir/evidence_timeseries.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

from scientific_discovery.run_discovery import main


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run multi-agent discovery on phenotyping results")
    ap.add_argument("--results-dir", type=Path, default=None, help="Directory with **/results.json")
    ap.add_argument("--out-dir", type=Path, default=None, help="Output directory for discovery artifacts")
    ap.add_argument("--no-llm", action="store_true", help="Disable LLM calls (use fallback outputs)")
    args = ap.parse_args()

    base = Path(__file__).parent
    results_dir = args.results_dir or (base / "SorghumO_over_time_results" / "SorghumO_over_time")
    out_dir = args.out_dir or (base / "SorghumO_over_time_discovery")

    argv = ["--results-dir", str(results_dir), "--out-dir", str(out_dir)]
    if args.no_llm:
        argv.append("--no-llm")
    raise SystemExit(main(argv))
