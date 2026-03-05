from __future__ import annotations

import json
import os
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


@dataclass(frozen=True)
class AgentRole:
    name: str
    goal: str
    constraints: List[str]


QC_AGENT = AgentRole(
    name="QC Agent",
    goal="Flag suspicious points; avoid false discoveries caused by bad masks or extraction failures.",
    constraints=[
        "Only cite evidence present in qc_flags and numeric time-series.",
        "Prefer conservative flags over speculative explanations.",
        "Return JSON only.",
    ],
)

EVENT_AGENT = AgentRole(
    name="Event Discovery Agent",
    goal="Find candidate events (stress onset, recovery, phase transitions) via change points and slope changes.",
    constraints=[
        "Only cite computed changepoints and time-series values.",
        "Do not invent treatments or external causes.",
        "Return JSON only.",
    ],
)

MECH_AGENT = AgentRole(
    name="Mechanism Agent",
    goal="Propose lag/lead relationships between spectral, texture, and morphology signals (causal ordering hypotheses).",
    constraints=[
        "Only cite computed lag correlations; state uncertainty.",
        "Avoid causal claims; use 'consistent with' language.",
        "Return JSON only.",
    ],
)

REPORTER_AGENT = AgentRole(
    name="Reporter Agent",
    goal="Write final conservative Discovery Report: 1–3 insights + evidence, QC caveats, and next analyses.",
    constraints=[
        "Use only evidence from other agents and computed tables.",
        "If QC flags are serious, down-rank confidence.",
        "Return JSON only.",
    ],
)


def _load_dotenv_if_present() -> None:
    """
    Minimal .env loader (no external dependency).
    Loads from project root .env if present.
    """
    try:
        root = Path(__file__).resolve().parents[1]  # project root
        env_path = root / ".env"
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if not k:
                continue
            if k in os.environ and os.environ.get(k):
                continue
            os.environ[k] = v
    except Exception:
        return


def _default_llm_config() -> Dict[str, Optional[str]]:
    """
    OpenAI-compatible chat-completions by default.
    Set: LLM_API_KEY, LLM_API_BASE (default: https://api.openai.com/v1), LLM_MODEL (default: gpt-4o-mini)
    """
    _load_dotenv_if_present()
    return {
        "api_key": os.environ.get("LLM_API_KEY"),
        "api_base": os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"),
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    }


def _call_chat_completions(*, api_key: str, api_base: str, model: str, messages: List[Dict[str, str]]) -> str:
    url = api_base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    max_retries = int(os.environ.get("LLM_MAX_RETRIES", "6"))
    base_sleep_s = float(os.environ.get("LLM_RETRY_BASE_SECONDS", "1.5"))
    verbose = os.environ.get("LLM_VERBOSE", "").strip().lower() in {"1", "true", "yes", "y", "on"}
    max_tokens_env = os.environ.get("LLM_MAX_TOKENS", "1200")
    try:
        max_tokens = int(max_tokens_env)
    except Exception:
        max_tokens = 1200
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }

    def _is_nonretryable_429(body_text: str) -> bool:
        try:
            data = json.loads(body_text or "{}")
            err = data.get("error") if isinstance(data, dict) else None
            if not isinstance(err, dict):
                return False
            code = str(err.get("code") or "").lower()
            typ = str(err.get("type") or "").lower()
            msg = str(err.get("message") or "").lower()
            nonretry = {"insufficient_quota", "billing_hard_limit_reached", "account_deactivated", "invalid_api_key"}
            if code in nonretry or typ in nonretry:
                return True
            if "insufficient quota" in msg or "billing" in msg or "hard limit" in msg:
                return True
        except Exception:
            pass
        return False

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=180)
            if r.status_code in {429, 500, 502, 503, 504}:
                if r.status_code == 429 and _is_nonretryable_429(r.text):
                    raise RuntimeError(f"LLM HTTP 429 (non-retryable). Response: {r.text[:2000]}")
                if attempt >= max_retries:
                    raise RuntimeError(f"LLM HTTP {r.status_code} after retries. Response: {r.text[:2000]}")

                retry_after = r.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = float(retry_after)
                    except Exception:
                        sleep_s = base_sleep_s * (2**attempt)
                else:
                    sleep_s = base_sleep_s * (2**attempt)
                if verbose:
                    print(f"[LLM] attempt {attempt+1}/{max_retries+1} got HTTP {r.status_code}; sleeping {min(60.0, sleep_s):.1f}s")
                time.sleep(min(60.0, sleep_s))
                continue

            if r.status_code >= 400:
                raise RuntimeError(f"LLM HTTP {r.status_code}. Response: {r.text[:2000]}")
            data = r.json()
            return str(data["choices"][0]["message"]["content"])
        except Exception as e:
            last_err = e
            if attempt >= max_retries:
                raise
            time.sleep(min(60.0, base_sleep_s * (2**attempt)))

    if last_err:
        raise last_err
    raise RuntimeError("LLM call failed for unknown reasons.")


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Could not parse JSON from LLM output.")


def run_agent_llm(
    role: AgentRole,
    evidence: Dict[str, Any],
    round_label: str,
    *,
    critique_of: Optional[Dict[str, Any]] = None,
    transcript: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    cfg = _default_llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("LLM_API_KEY not set")

    constraints = "\n".join([f"- {c}" for c in role.constraints])
    critique_block = ""
    if critique_of is not None:
        critique_block = "\n\nCRITIQUE THIS AGENT OUTPUT (JSON):\n" + json.dumps(critique_of, indent=2)

    prompt = textwrap.dedent(
        f"""
        You are {role.name}.
        Goal: {role.goal}
        Constraints:
        {constraints}

        ROUND: {round_label}

        EVIDENCE (JSON):
        {json.dumps(evidence, indent=2)}
        {critique_block}

        Output STRICT JSON with this shape:
        {{
          "agent": "{role.name}",
          "round": "{round_label}",
          "claims": [{{"title": "...", "description": "...", "evidence": [ ... ], "confidence": 0.0}}],
          "qc_caveats": [ ... ],
          "recommended_next_steps": [ ... ]
        }}
        """
    ).strip()

    messages = [
        {"role": "system", "content": "You are a scientific analysis assistant. Output JSON only."},
        {"role": "user", "content": prompt},
    ]
    text = _call_chat_completions(
        api_key=str(cfg["api_key"]),
        api_base=str(cfg["api_base"]),
        model=str(cfg["model"]),
        messages=messages,
    )

    if transcript is not None:
        transcript.append(
            {
                "agent": role.name,
                "round": round_label,
                "llm": {
                    "api_base": str(cfg.get("api_base")),
                    "model": str(cfg.get("model")),
                },
                "messages": messages,
                "raw_response_text": text,
            }
        )

    return _extract_json(text)


def run_agent_fallback(role: AgentRole, evidence: Dict[str, Any], round_label: str, critique_of: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """No-LLM fallback: create conservative, evidence-only outputs."""
    claims: List[Dict[str, Any]] = []
    qc_caveats: List[str] = []
    next_steps: List[str] = []

    if role.name == "QC Agent":
        flags = evidence.get("qc_flags", [])
        if flags:
            qc_caveats.append(f"{len(flags)} QC flag(s) detected; review masks/overlays at flagged dates.")
        claims.append(
            {
                "title": "QC summary",
                "description": "QC flags are derived from mask area stability and instance counts. Use them to down-weight suspect timepoints.",
                "evidence": flags[:10],
                "confidence": 0.7 if not flags else 0.5,
            }
        )
        next_steps.append("Manually inspect overlay.png for any flagged dates and consider re-running with a different prompt/threshold.")

    elif role.name == "Event Discovery Agent":
        cps = evidence.get("changepoints", [])
        if cps:
            claims.append(
                {
                    "title": "Candidate events from change points",
                    "description": "Large robust jumps in first-differences suggest stress/recovery/phase transitions (interpret conservatively).",
                    "evidence": cps[:8],
                    "confidence": 0.55,
                }
            )
        else:
            claims.append(
                {
                    "title": "No strong change points detected",
                    "description": "With current thresholds, signals look gradual or too sparse/noisy for robust event detection.",
                    "evidence": [],
                    "confidence": 0.6,
                }
            )
        next_steps.append("Tune change-point z-threshold and/or increase sampling frequency for sharper event detection.")

    elif role.name == "Mechanism Agent":
        lags = evidence.get("lag_relationships", [])
        if lags:
            claims.append(
                {
                    "title": "Lead/lag hypotheses",
                    "description": "Best correlations between spectral indices and morphology growth slope suggest possible temporal ordering.",
                    "evidence": lags[:5],
                    "confidence": 0.5,
                }
            )
        else:
            claims.append(
                {
                    "title": "No reliable lag relationships found",
                    "description": "Time-series is sparse and/or signals are noisy; correlations did not meet reliability thresholds.",
                    "evidence": [],
                    "confidence": 0.6,
                }
            )
        next_steps.append("Add more timepoints or additional signals to strengthen lag inference.")

    else:  # Reporter
        qc = evidence.get("qc_flags", [])
        cps = evidence.get("changepoints", [])
        lags = evidence.get("lag_relationships", [])
        conf = 0.55
        if qc:
            qc_caveats.append("QC flags present; treat quantitative jumps with caution.")
            conf = 0.45
        claims.append(
            {
                "title": "Discovery summary (evidence-first)",
                "description": "This report summarizes candidate events and lag relationships computed from the extracted features.",
                "evidence": {"top_changepoints": cps[:5], "top_lags": lags[:3], "qc_flags": qc[:5]},
                "confidence": conf,
            }
        )
        next_steps.extend(
            [
                "Re-run segmentation with a prompt that consistently targets the same plant.",
                "Add an uncertainty check: bootstrap time-series correlations after dropping 1 timepoint at a time.",
                "If you add more plants, repeat discovery and look for consistent event timings across replicates.",
            ]
        )

    return {
        "agent": role.name,
        "round": round_label,
        "claims": claims,
        "qc_caveats": qc_caveats,
        "recommended_next_steps": next_steps,
        "llm_used": False,
    }


def run_multi_agent_lab(
    evidence: Dict[str, Any],
    *,
    use_llm_if_available: bool = True,
    transcript: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    2-round debate:
    - Round 1: each agent proposes
    - Round 2: Reporter synthesizes and critiques weak claims
    """
    cfg = _default_llm_config()
    llm_available = bool(cfg.get("api_key")) if use_llm_if_available else False

    def run(role: AgentRole, round_label: str, critique_of: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if llm_available:
            out = run_agent_llm(role, evidence, round_label, critique_of=critique_of, transcript=transcript)
            out["llm_used"] = True
            return out
        out = run_agent_fallback(role, evidence, round_label, critique_of=critique_of)
        if transcript is not None:
            transcript.append(
                {
                    "agent": role.name,
                    "round": round_label,
                    "llm_used": False,
                    "evidence": evidence,
                    "critique_of": critique_of,
                    "output": out,
                }
            )
        return out

    round1 = {
        "qc": run(QC_AGENT, "round1"),
        "events": run(EVENT_AGENT, "round1"),
        "mechanism": run(MECH_AGENT, "round1"),
    }
    reporter_input = {"round1": round1}
    round2_reporter = run(REPORTER_AGENT, "round2", critique_of=reporter_input)

    return {
        "llm_available": llm_available,
        "round1": round1,
        "round2": {"reporter": round2_reporter},
    }
