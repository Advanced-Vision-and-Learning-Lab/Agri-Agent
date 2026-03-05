from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _parse_iso_date(s: str) -> Optional[date]:
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def extract_date(value: str) -> Optional[date]:
    """
    Extract an ISO date from a filename/stem/path string.
    Example: '2025-04-21__plant1_frame8' -> 2025-04-21
    """
    if not value:
        return None
    m = _DATE_RE.search(str(value))
    if not m:
        return None
    return _parse_iso_date(m.group(1))


@dataclass(frozen=True)
class ResultRecord:
    path: Path
    date: Optional[date]
    image_name: str
    image_path: str
    raw: Dict[str, Any]


def iter_results_json(results_root: Path) -> Iterable[Path]:
    yield from results_root.rglob("results.json")


def load_result(path: Path) -> ResultRecord:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    image_name = str(raw.get("image_name") or raw.get("plant_name") or path.parent.name)
    image_path = str(raw.get("image_path") or "")
    dt = extract_date(image_name) or extract_date(image_path) or extract_date(str(path))
    return ResultRecord(path=path, date=dt, image_name=image_name, image_path=image_path, raw=raw)


def load_all(results_root: Path) -> List[ResultRecord]:
    records: List[ResultRecord] = []
    for p in sorted(iter_results_json(results_root)):
        try:
            records.append(load_result(p))
        except Exception as e:
            raise RuntimeError(f"Failed to load {p}: {e}") from e

    records.sort(key=lambda r: (r.date or date.max, r.image_name))
    return records
