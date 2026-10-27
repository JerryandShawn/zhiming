"""Bind an R11 assessment and all original reports to this exact local candidate."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mingjing_core.models.quota_r11 import REQUIRED, validate_r11, validate_raw_reports
from mingjing_core.models.quota_r16 import K31ConnectionApproval, connection_approval
from mingjing_core.models.quota_types import GuardRejected
from tools.eval.contracts import scenario_contract_hash
from tools.eval.live import candidate_provenance
from tools.eval.schema import load_scenario

ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path, boundary: Path, limit: int) -> dict[str, Any]:
    path = path.absolute()
    if not path.resolve().is_relative_to(boundary.resolve()) or any(
        part.is_symlink() for part in (path, *path.parents)
    ):
        raise GuardRejected("batch_conflict")
    if not path.is_file() or path.stat().st_size > limit:
        raise GuardRejected("manual_start_required")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GuardRejected("manual_start_required")
    return value


def candidate_r11(path: Path, candidate: str, now: datetime) -> K31ConnectionApproval:
    from tools.eval.runner import _source_digest

    candidate_provenance(ROOT, candidate)
    boundary = ROOT / "private/candidate-eval" / candidate
    value = _read(path, boundary, 32768)
    validate_r11(value, candidate)
    if value.get("synthetic") is not False or value["source_sha256"] != _source_digest():
        raise GuardRejected("batch_conflict")
    report_paths = value.get("reports")
    if not isinstance(report_paths, dict) or set(report_paths) != set(REQUIRED):
        raise GuardRejected("manual_start_required")
    reports = {}
    for name, relative in report_paths.items():
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise GuardRejected("batch_conflict")
        reports[name] = _read(ROOT / relative, boundary, 64 * 1024 * 1024)
    validate_raw_reports(value, reports)
    contract = scenario_contract_hash(load_scenario(ROOT / "tools/eval/scenarios/X02.yaml"))
    if value["x02_equivalent"]["original_contract_sha256"] != contract:
        raise GuardRejected("batch_conflict")
    candidate_provenance(ROOT, candidate)
    if value["source_sha256"] != _source_digest():
        raise GuardRejected("batch_conflict")
    return connection_approval(value, candidate, now)
