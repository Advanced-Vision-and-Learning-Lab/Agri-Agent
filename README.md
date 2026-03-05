# Agri-Agent

**LLM-powered scientific discovery over plant phenotyping time-series data.**

Part of the [Advanced Vision and Learning Lab](https://github.com/Advanced-Vision-and-Learning-Lab) research.

This package turns per-image `results.json` outputs from a phenotyping pipeline into:
- a cleaned time-series evidence table
- QC flags (mask stability, segmentation anomalies)
- change-point / event candidates (stress onset, recovery, phase transitions)
- lag / lead relationships between spectral, texture, and morphology signals
- **Discovery Reports** (JSON + Markdown) via multi-agent LLM analysis

---

## Overview

The discovery pipeline consumes `results.json` files produced by plant phenotyping (segmentation + feature extraction). It builds an evidence table, runs analytics (changepoints, lag correlations), and optionally uses LLM agents to synthesize conservative, evidence-backed discovery summaries.

**Two modes:**
1. **Multi-agent lab** (`discover_sorghum_over_time.py`): QC → Events → Mechanism → Reporter (2-round debate)
2. **Single Reporter** (`run_one_agent_reporter.py`): One Reporter agent with minimal evidence (faster, cheaper)

---

## PhD-level thesis step (add one thing)

Add a **Hypothesis–Test loop**: after the agents propose discoveries, a dedicated **Verifier Agent** automatically turns each claim into *falsifiable hypotheses* and runs *pre-registered statistical checks* (e.g., permutation tests, holdout timepoints, bootstrap stability, multi-plant replication), then forces the Reporter to **revise confidence** and label claims as *supported / inconclusive / rejected* with exact test outputs.

---

## Installation

```bash
# Clone the repo
git clone https://github.com/Advanced-Vision-and-Learning-Lab/Agri-Agent.git
cd Agri-Agent

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Requirements

- **Input**: A directory tree containing `results.json` files (one per image/date)
- **results.json** must include:
  - `image_name` or `plant_name` (with date in YYYY-MM-DD format)
  - `vegetation_indices`, `texture_features`, `morphology_features` (nested dicts with numeric stats)
  - `mask_area_pixels`

Example structure:
```
results_dir/
├── 2025-04-01__plant1_frame8/
│   └── results.json
├── 2025-04-15__plant1_frame8/
│   └── results.json
└── ...
```

---

## Usage

### 1. Aggregate results (optional)

If you have raw phenotyping output, aggregate it into timeseries CSV/JSON:

```bash
python aggregate_sorghum_over_time.py --results-dir /path/to/phenotyping_output --output timeseries
```

Outputs: `timeseries.csv`, `timeseries.json`, `summary_for_ai.md`

### 2. Multi-agent discovery (full pipeline)

```bash
python discover_sorghum_over_time.py \
  --results-dir /path/to/results \
  --out-dir ./discovery_output
```

With `--no-llm`, runs without LLM calls (evidence-only fallback outputs).

**Outputs:**
- `discovery_report.json` – full report with agent lab outputs
- `discovery_report.md` – human-readable markdown
- `evidence_timeseries.csv` – flattened evidence table

### 3. Single Reporter agent (lightweight)

```bash
python run_one_agent_reporter.py \
  --results-dir /path/to/results \
  --out-dir ./discovery_output
```

**Output:** `one_agent_reporter.json` – 1–3 conservative discovery bullets backed by evidence.

---

## LLM Configuration

Uses OpenAI-compatible chat-completions API. Set environment variables:

| Variable      | Description                    | Default                |
|---------------|--------------------------------|------------------------|
| `LLM_API_KEY` | API key (required for LLM)     | —                      |
| `LLM_API_BASE`| API base URL                   | `https://api.openai.com/v1` |
| `LLM_MODEL`   | Model name                     | `gpt-4o-mini`          |
| `LLM_MAX_TOKENS` | Max tokens per response    | `1200`                 |
| `LLM_MAX_RETRIES` | Retries on 429/5xx        | `6`                    |

Or create a `.env` file in the project root:

```
LLM_API_KEY=sk-...
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Without `LLM_API_KEY`, the pipeline uses **fallback outputs** (no LLM calls).

---

## Project Structure

```
Agri-Agent/
├── scientific_discovery/       # Core discovery module
│   ├── __init__.py
│   ├── io.py                  # Load results.json
│   ├── evidence.py             # Build evidence table, pick signals
│   ├── analytics.py            # Changepoints, lag search, QC flags
│   ├── agent_lab.py            # LLM agents (QC, Events, Mechanism, Reporter)
│   ├── render.py               # JSON + Markdown output
│   └── run_discovery.py        # Main discovery logic
├── discover_sorghum_over_time.py   # Multi-agent discovery script
├── run_one_agent_reporter.py      # Single Reporter script
├── aggregate_sorghum_over_time.py # Timeseries aggregation
├── requirements.txt
└── README.md
```

---

## Dependencies

- `numpy`
- `pandas`
- `requests` (for LLM API calls)

No heavy ML dependencies; works with any phenotyping pipeline that outputs `results.json`.

---

## Citation

If you use this software in your research, please cite appropriately.

**Author:** Fahime Horvatinia  
**Organization:** Advanced Vision and Learning Lab  
**Repository:** https://github.com/Advanced-Vision-and-Learning-Lab/Agri-Agent
