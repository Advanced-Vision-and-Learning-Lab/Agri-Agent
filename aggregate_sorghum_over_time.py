#!/usr/bin/env python3
"""
Aggregate pipeline results from phenotyping output into a single timeseries CSV/JSON.
Designed for AI agents to track plant changes over time and extract meaningful insights.

Usage:
  python aggregate_sorghum_over_time.py [--results-dir RESULTS_DIR] [--output timeseries]

Output:
  - timeseries.csv: One row per date with all numeric features
  - timeseries.json: Full structured data for programmatic analysis
  - summary_for_ai.md: Human-readable summary with key metrics for AI context
"""
import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def extract_date_from_stem(stem: str) -> Optional[str]:
    """Extract YYYY-MM-DD from stem like '2024-12-04__plant1_frame8'."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    return m.group(1) if m else None


def flatten_dict(d: Dict, prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dict for CSV; only include numeric values."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}" if prefix else k
        if isinstance(v, dict):
            if "mean" in v or "min" in v or "max" in v or "std" in v:
                for sk, sv in v.items():
                    if isinstance(sv, (int, float)) and not isinstance(sv, bool):
                        out[f"{key}_{sk}"] = sv
            else:
                out.update(flatten_dict(v, f"{key}_"))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = v
    return out


def load_results(results_dir: Path) -> List[Dict]:
    """Load all results.json from the results directory."""
    results = []
    for p in results_dir.rglob("results.json"):
        try:
            with open(p) as f:
                data = json.load(f)
            data["_source_file"] = str(p)
            data["_output_dir"] = str(p.parent)
            results.append(data)
        except Exception as e:
            print(f"Warning: Could not load {p}: {e}")
    return results


def _flatten_into_row(prefix: str, d: Dict, row: Dict) -> None:
    """Recursively add numeric values from d into row with prefix."""
    for k, v in d.items():
        key = f"{prefix}_{k}" if prefix else k
        if isinstance(v, dict):
            _flatten_into_row(key, v, row)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            row[key] = v


def build_timeseries_rows(results: List[Dict]) -> List[Dict]:
    """Build flat rows for timeseries, one per image, sorted by date."""
    rows = []
    for r in results:
        stem = r.get("image_name") or r.get("plant_name") or Path(r.get("image_path", "")).stem
        date = extract_date_from_stem(stem) or "unknown"
        row = {"date": date, "stem": stem, "image_path": r.get("image_path", "")}

        _flatten_into_row("veg", r.get("vegetation_indices", {}), row)
        _flatten_into_row("tex", r.get("texture_features", {}), row)
        _flatten_into_row("morph", r.get("morphology_features", {}), row)
        row["mask_area_pixels"] = r.get("mask_area_pixels")

        rows.append(row)

    rows.sort(key=lambda x: (x["date"], x["stem"]))
    return rows


def rows_to_csv(rows: List[Dict]) -> str:
    """Convert rows to CSV string."""
    if not rows:
        return ""
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    cols = ["date", "stem", "image_path"] + sorted(k for k in all_keys if k not in ("date", "stem", "image_path"))
    lines = [",".join(str(r.get(c, "")) for c in cols) for r in rows]
    return ",".join(cols) + "\n" + "\n".join(lines)


def write_summary_for_ai(rows: List[Dict], output_path: Path) -> None:
    """Write a summary markdown file for AI agents."""
    lines = [
        "# Sorghum Plant Timeseries Summary",
        "",
        "## Overview",
        f"- **Number of timepoints:** {len(rows)}",
        f"- **Date range:** {rows[0]['date']} to {rows[-1]['date']}" if rows else "N/A",
        "",
        "## Key Metrics Over Time",
        "",
    ]

    all_keys = list(rows[0].keys()) if rows else []
    priority = ["morph_area_cm2", "morph_skeleton_length_cm", "mask_area_pixels", "morph_perimeter_cm"]
    morph_keys = [k for k in priority if k in all_keys]
    morph_keys += [k for k in all_keys if k.startswith("morph_") and k not in morph_keys][:3]
    veg_keys = [k for k in all_keys if k.startswith("veg_") and "mean" in k][:3]

    table_cols = morph_keys + veg_keys
    if table_cols:
        header_cols = ["Date"] + table_cols[:8]
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")
        for r in rows[:20]:
            vals = [r["date"]] + [str(r.get(k, ""))[:12] for k in header_cols[1:]]
            lines.append("| " + " | ".join(vals) + " |")

    lines.extend([
        "",
        "## For AI Analysis",
        "",
        "- Use `timeseries.csv` for numeric trends (growth, vegetation indices, morphology).",
        "- Use `timeseries.json` for full structured data.",
        "- Look for: mask_area_pixels (plant size proxy), morphology features (shape), vegetation indices (health).",
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Aggregate phenotyping pipeline results for AI analysis")
    ap.add_argument("--results-dir", type=Path, default=None, help="Results directory (default: SorghumO_over_time_results)")
    ap.add_argument("--output", type=str, default="timeseries", help="Output base name (without extension)")
    args = ap.parse_args()

    base = Path(__file__).parent
    results_dir = args.results_dir or (base / "SorghumO_over_time_results")
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        print("Provide --results-dir with path to phenotyping output containing results.json files.")
        return 1

    results = load_results(results_dir)
    if not results:
        print("No results.json files found.")
        return 1

    rows = build_timeseries_rows(results)
    out_base = base / args.output

    csv_path = Path(str(out_base) + ".csv")
    csv_path.write_text(rows_to_csv(rows), encoding="utf-8")
    print(f"Wrote {csv_path}")

    json_path = Path(str(out_base) + ".json")
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"Wrote {json_path}")

    summary_path = base / "summary_for_ai.md"
    write_summary_for_ai(rows, summary_path)
    print(f"Wrote {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
