"""No production authorization is created by these synthetic policy fixtures."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest

from mingjing_core.models.provider_reset import retry_after
from mingjing_core.models.quota_delegated import _SEAL, DelegatedApproval, approval_from_gate
from mingjing_core.models.quota_gate import REQUIRED
from mingjing_core.models.quota_types import GuardRejected

NOW = datetime(2026, 10, 24, tzinfo=UTC)
CANDIDATE = "a" * 40


def gate(equivalent: bool | None = None) -> dict:
    value = {
        "schema": "first-release-scripted-gate-v1",
        "candidate_commit": CANDIDATE,
        "equivalent": equivalent,
        "source_sha256": "b" * 64,
        "synthetic": True,
        "worktree_clean": True,
    }
    for name, identities in REQUIRED.items():
        value[name] = {
            "mode": "scripted",
            "target": "v4",
            "status": "complete",
            "count": len(identities),
            "passed": len(identities),
            "case_ids": sorted(identities),
            "candidate_commit": CANDIDATE,
            "source_sha256": "b" * 64,
            "physical_requests": 0,
            "worktree_clean": True,
        }
    return value


def synthetic_approval(equivalent: bool | None = True) -> DelegatedApproval:
    """Test-only core fixture; production has no trusted equivalence issuer yet."""
    approval = approval_from_gate(gate(), CANDIDATE, NOW)
    return replace(approval, equivalent=equivalent, _seal=(_SEAL, CANDIDATE, approval.expires_at, equivalent))


@pytest.mark.parametrize("equivalent", [True, False])
def test_scripted_gate_cannot_self_attest_real_equivalence(equivalent: bool) -> None:
    with pytest.raises(GuardRejected) as caught:
        approval_from_gate(gate(equivalent), CANDIDATE, NOW)
    assert caught.value.kind == "manual_start_required"


@pytest.mark.parametrize(
    "key,field,value",
    [
        ("p3", "passed", 47),
        ("core", "passed", 58),
        ("core", "count", 80),
        ("core", "target", "v3"),
        ("p3", "mode", "live"),
        ("core", "status", "pending"),
        ("date_checks", "passed", 6),
        ("core", "physical_requests", 1),
        ("p3", "candidate_commit", "c" * 40),
        ("core", "source_sha256", "d" * 64),
        ("date_checks", "worktree_clean", False),
    ],
)
def test_incomplete_or_wrong_target_cannot_issue_delegation(key: str, field: str, value: object) -> None:
    proof = gate()
    proof[key][field] = value
    with pytest.raises(GuardRejected):
        approval_from_gate(proof, CANDIDATE, NOW)


def test_correct_count_cannot_hide_wrong_or_duplicated_scenarios() -> None:
    for key, identities in (
        ("core", ["X03"] + sorted(REQUIRED["core"])[1:]),
        ("date_checks", ["TR01"] * 7),
    ):
        proof = gate()
        proof[key]["case_ids"] = identities
        with pytest.raises(GuardRejected):
            approval_from_gate(proof, CANDIDATE, NOW)


def test_approval_is_candidate_and_result_bound_and_expires() -> None:
    approval = approval_from_gate(gate(), CANDIDATE, NOW)
    for changed in (
        {"candidate": "b" * 40},
        {"equivalent": False},
        {"expires_at": NOW + timedelta(days=1)},
    ):
        with pytest.raises(GuardRejected):
            replace(approval, **changed).check(NOW)
    with pytest.raises(GuardRejected):
        approval.check(approval.expires_at)
    with pytest.raises(GuardRejected):
        approval_from_gate(gate(), "b" * 40, NOW)


def test_only_explicit_future_standard_reset_is_accepted() -> None:
    target = NOW + timedelta(hours=5)
    assert retry_after("18000", NOW) == retry_after(format_datetime(target, usegmt=True), NOW) == target
    for value in (
        None,
        "",
        "-1",
        "soon",
        "0",
        "in 5 hours",
        "9999999999999999999999",
        "900000",
    ):
        assert retry_after(value, NOW) is None
    assert retry_after(format_datetime(NOW - timedelta(hours=1), usegmt=True), NOW) is None


def test_synthetic_fixture_is_never_accepted_by_the_real_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import member_delegate

    monkeypatch.setattr(
        member_delegate.subprocess,
        "check_output",
        lambda command, **kwargs: CANDIDATE if command[1] == "rev-parse" else "",
    )
    path = tmp_path / "synthetic-not-a-real-gate.json"
    path.write_text(json.dumps(gate()), encoding="utf-8")
    with pytest.raises(GuardRejected) as caught:
        member_delegate.candidate_gate(path, CANDIDATE, NOW)
    assert caught.value.kind == "manual_start_required"
