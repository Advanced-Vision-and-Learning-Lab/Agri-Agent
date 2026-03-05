from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _md_table(rows: List[Dict[str, Any]], columns: List[str], max_rows: int = 20) -> str:
    if not rows or not columns:
        return ""
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for r in rows[:max_rows]:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
    return "\n".join(lines)


def write_discovery_markdown(report: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = report.get("summary", {})
    evidence = report.get("evidence_overview", {})
    qc = report.get("qc_flags", [])
    cps = report.get("changepoints", [])
    lags = report.get("lag_relationships", [])
    agent_lab = report.get("agent_lab", {})

    lines: List[str] = []
    lines.append("# Discovery Report (Sorghum over time)")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- **Timepoints:** {summary.get('n_timepoints', 'NA')}")
    lines.append(f"- **Date range:** {summary.get('date_range', 'NA')}")
    lines.append(f"- **Signals used:** {', '.join(summary.get('signals_used', [])) or 'NA'}")
    lines.append("")

    if evidence:
        lines.append("## Evidence overview")
        for k, v in evidence.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    lines.append("## QC flags (top)")
    if qc:
        lines.append(_md_table(qc, ["date", "type", "value", "ratio_vs_prev"], max_rows=15))
    else:
        lines.append("No QC flags.")
    lines.append("")

    lines.append("## Change points (top)")
    if cps:
        lines.append(_md_table(cps, ["date", "column", "kind", "magnitude", "z"], max_rows=15))
    else:
        lines.append("No strong change points detected at current thresholds.")
    lines.append("")

    lines.append("## Lag relationships (top)")
    if lags:
        lines.append(_md_table(lags, ["lead_signal", "response_signal", "lag_days", "corr", "n"], max_rows=15))
    else:
        lines.append("No reliable lag relationships computed.")
    lines.append("")

    lines.append("## Agent lab outputs")
    if agent_lab:
        lines.append(f"- **LLM available:** {agent_lab.get('llm_available')}")
        lines.append("")
        r1 = agent_lab.get("round1", {})
        for k in ["qc", "events", "mechanism"]:
            a = r1.get(k, {})
            lines.append(f"### {a.get('agent', k)} (round1)")
            for c in a.get("claims", [])[:3]:
                lines.append(f"- **{c.get('title','')}** (conf={c.get('confidence','')})")
                desc = str(c.get("description", "")).strip()
                if desc:
                    lines.append(f"  - {desc}")
            lines.append("")

        rep = agent_lab.get("round2", {}).get("reporter", {})
        lines.append(f"### {rep.get('agent','Reporter')} (round2)")
        for c in rep.get("claims", [])[:3]:
            lines.append(f"- **{c.get('title','')}** (conf={c.get('confidence','')})")
            desc = str(c.get("description", "")).strip()
            if desc:
                lines.append(f"  - {desc}")
        lines.append("")
    else:
        lines.append("Agent lab not run.")
        lines.append("")

    lines.append("## Next steps")
    next_steps = report.get("next_steps", [])
    if next_steps:
        for s in next_steps:
            lines.append(f"- {s}")
    else:
        lines.append("- Add more plants/timepoints; rerun discovery for consistency across replicates.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_json(report: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
