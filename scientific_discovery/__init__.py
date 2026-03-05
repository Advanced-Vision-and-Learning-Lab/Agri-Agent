"""
Scientific discovery layer on top of phenotyping pipeline results.

This package turns per-image `results.json` outputs into:
- a cleaned time-series evidence table
- QC flags
- change-point / event candidates
- lag / lead relationships between signals
- a Discovery Report (JSON + Markdown) via LLM agents
"""
