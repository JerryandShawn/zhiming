"""Synthetic evidence exercises R16 policy; it is not a real operator approval."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from mingjing_core.models.quota_delegated import delegated_stage
from mingjing_core.models.quota_gate import CORE_IDS
from mingjing_core.models.quota_r11 import DEFERRED_IDS, REQUIRED, validate_raw_reports
from mingjing_core.models.quota_r16 import connection_approval
from mingjing_core.models.quota_types import GuardRejected

from .test_delegated_policy import CANDIDATE, NOW, gate, synthetic_approval


def fixture_gate() -> tuple[dict, dict]:
    value = {
        "schema": "first-release-scripted-gate-r11",
        "candidate_commit": CANDIDATE,
        "source_sha256": "b" * 64,
        "worktree_clean": True,
        "equivalent": None,
        "synthetic": True,
        "original_core_count": 81,
        "deferred": dict.fromkeys(DEFERRED_IDS, "synthetic deferred"),
        "x02_equivalent": {
            "id": "X02-r11",
            "status": "passed",
            "score": 1,
            "mock_http_requests": 4,
            "external_provider_requests": 0,
            "repeat_writes": 0,
            "friendly_failure": True,
            "committed_answer_preserved": True,
            "original_contract_sha256": "c" * 64,
        },
    }
    reports = {}
    for name, expected in REQUIRED.items():
        value[name] = {
            "mode": "scripted",
            "target": "v4",
            "status": "complete",
            "raw_report_status": "incomplete" if name == "core" else "complete",
            "candidate_commit": CANDIDATE,
            "source_sha256": "b" * 64,
            "worktree_clean": True,
            "count": len(expected),
            "passed": len(expected),
            "physical_requests": 0,
            "case_ids": sorted(expected),
        }
        reports[name] = {
            "metadata": {
                **value[name],
                "status": value[name]["raw_report_status"],
                "external_provider_requests": 0,
            },
            "cases": [
                {
                    "id": identity,
                    "status": "passed" if identity in expected else "failed",
                    "score": 1.0 if identity in expected else 0.0,
                    "v4_evidence": {"external_provider_requests": 0},
                }
                for identity in sorted(CORE_IDS if name == "core" else expected)
            ],
        }
    return value, reports


def test_r11_raw_scope_keeps_original_failures_and_never_issues_core_approval() -> None:
    value, reports = fixture_gate()
    validate_raw_reports(value, reports)
    assert reports["core"]["metadata"]["status"] == "incomplete"
    assert sum(row["status"] == "failed" for row in reports["core"]["cases"]) == 12
    approval = connection_approval(value, CANDIDATE, NOW)
    assert delegated_stage(approval, "k31-connect") == "k31-connect"
    for phase in ("core", "equivalence", "core-k31"):
        with pytest.raises(GuardRejected):
            delegated_stage(approval, phase)
    for old in (synthetic_approval(), synthetic_approval(False)):
        with pytest.raises(GuardRejected):
            delegated_stage(old, "k31-connect")
    with pytest.raises(GuardRejected):
        connection_approval(gate(), CANDIDATE, NOW)
    with pytest.raises(GuardRejected):
        replace(approval, source_sha256="d" * 64).check(NOW)


def test_r11_raw_scope_cannot_hide_missing_or_failed_required_cases_or_foreign_source() -> None:
    value, reports = fixture_gate()
    for change in ("failed", "missing", "duplicate", "foreign", "real", "pending", "boolean-score"):
        changed = deepcopy(reports)
        case = next(row for row in changed["core"]["cases"] if row["id"] == "C01")
        if change == "failed":
            case.update(status="failed", score=0.0)
        elif change == "missing":
            changed["core"]["cases"].remove(case)
        elif change == "duplicate":
            changed["core"]["cases"][-1] = deepcopy(case)
        elif change == "foreign":
            changed["core30"]["metadata"]["source_sha256"] = "e" * 64
        elif change == "real":
            case["v4_evidence"]["external_provider_requests"] = 1
        elif change == "pending":
            changed["core"]["cases"][-1]["status"] = "incomplete"
        else:
            case["score"] = True
        with pytest.raises(GuardRejected):
            validate_raw_reports(value, changed)
    for section, field, invalid in (
        ("core", "count", 81),
        ("p3", "passed", 47),
        ("date_checks", "physical_requests", False),
        ("x02_equivalent", "repeat_writes", 1),
        ("x02_equivalent", "committed_answer_preserved", False),
    ):
        changed = deepcopy(value)
        changed[section][field] = invalid
        with pytest.raises(GuardRejected):
            connection_approval(changed, CANDIDATE, NOW)


def test_r11_operator_rereads_raw_reports_and_rejects_synthetic_or_foreign_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.eval import r11_gate, runner

    value, reports = fixture_gate()
    value["synthetic"] = False
    boundary = tmp_path / "private/candidate-eval" / CANDIDATE
    boundary.mkdir(parents=True)
    value["reports"] = {}
    for name, report in reports.items():
        path = boundary / f"{name}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        value["reports"][name] = str(path.relative_to(tmp_path))
    path = boundary / "assessment.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(r11_gate, "ROOT", tmp_path)
    provenance = []
    monkeypatch.setattr(r11_gate, "candidate_provenance", lambda *args: provenance.append(args))
    monkeypatch.setattr(runner, "_source_digest", lambda: "b" * 64)
    monkeypatch.setattr(r11_gate, "load_scenario", lambda _: None)
    monkeypatch.setattr(r11_gate, "scenario_contract_hash", lambda _: "c" * 64)
    assert r11_gate.candidate_r11(path, CANDIDATE, NOW).candidate == CANDIDATE
    assert len(provenance) == 2
    outside = boundary.parent / "outside.json"
    outside.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(GuardRejected):
        r11_gate.candidate_r11(boundary / "../outside.json", CANDIDATE, NOW)
    raw = boundary / "core.json"
    original = raw.read_text(encoding="utf-8")
    altered = json.loads(original)
    altered["cases"][0]["status"] = "failed"
    raw.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(GuardRejected):
        r11_gate.candidate_r11(path, CANDIDATE, NOW)
    raw.write_text(original, encoding="utf-8")
    for field, invalid in (("synthetic", True), ("source_sha256", "f" * 64)):
        changed = {**value, field: invalid}
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(GuardRejected):
            r11_gate.candidate_r11(path, CANDIDATE, NOW)
    path.write_text(json.dumps(value), encoding="utf-8")
    value["reports"]["core"] = "../outside.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(GuardRejected):
        r11_gate.candidate_r11(path, CANDIDATE, NOW)


def test_first_release_profile_is_part_of_scripted_source_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.eval import runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    profile = tmp_path / "config/models.first-release.yaml"
    profile.parent.mkdir()
    profile.write_text("model: k3.1-pro\nreasoning_effort: high\n", encoding="utf-8")
    before = runner._source_digest()
    profile.write_text("model: k3.1-pro-highspeed\nreasoning_effort: high\n", encoding="utf-8")
    assert runner._source_digest() != before
