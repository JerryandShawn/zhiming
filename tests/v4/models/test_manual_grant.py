"""Receipts only reference existing authority; writing protects capability metadata."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.timekit.clock import SystemClock
from tools.manual_grant import evaluation_scope, load_manual_grant
from tools.manual_grant_io import write_private_receipt


def receipt() -> dict[str, Any]:
    return {
        "schema": "member-manual-start-v1",
        "suite": "PROBE",
        "batch_number": 1,
        "batch_id": "manual-probe-1-synthetic",
        "authorization_id": "terminal-synthetic",
        "scenario_ids": ["text_stream"],
        "expires_at": (SystemClock().now() + timedelta(minutes=10)).isoformat(),
        "automatic_next_batch": False,
        "model_calls": 0,
    }


def store(tmp_path: Path, value: dict[str, Any]) -> Path:
    path = tmp_path / "grant.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_receipt_references_one_existing_batch_and_scope_does_not_renew(
    tmp_path: Path,
) -> None:
    path = store(tmp_path, receipt())
    before = path.read_bytes()
    grant = load_manual_grant(path, "PROBE", ["text_stream"])
    scope = grant.scope("text_stream")
    assert (scope.lane, scope.batch_id, scope.authorization_id, scope.scenario_id) == (
        "probe",
        grant.batch_id,
        grant.authorization_id,
        "text_stream",
    )
    assert path.read_bytes() == before
    with pytest.raises(GuardRejected) as error:
        grant.scope("next-batch")
    assert error.value.kind == "batch_conflict"


@pytest.mark.parametrize(
    "change",
    [
        {"automatic_next_batch": True},
        {"model_calls": 1},
        {"model_calls": False},
        {"suite": "E1"},
        {"batch_number": True},
        {"batch_number": 0},
        {"scenario_ids": []},
        {"scenario_ids": ["text_stream"] * 2},
        {"schema": "future"},
        {"extra": "private body must not escape"},
    ],
)
def test_invalid_receipts_fail_before_any_network(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(GuardRejected) as error:
        load_manual_grant(store(tmp_path, receipt() | change), "PROBE", ["text_stream"])
    assert "private" not in str(error.value) and error.value.kind == "manual_start_required"


@pytest.mark.parametrize("expires", ["2020-01-01T00:00:00+00:00", "2030-01-01T00:00:00"])
def test_expired_or_naive_authority_is_rejected(tmp_path: Path, expires: str) -> None:
    with pytest.raises(GuardRejected) as error:
        load_manual_grant(store(tmp_path, receipt() | {"expires_at": expires}), "PROBE", [])
    assert error.value.kind == "authorization_expired"


def test_unapproved_requested_scenario_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(GuardRejected) as error:
        load_manual_grant(store(tmp_path, receipt()), "PROBE", ["single_tool"])
    assert error.value.kind == "manual_start_required"


def test_reference_environment_does_not_create_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mingjing_core.models.quota_runtime import current_scope

    monkeypatch.delenv("MEMBER_GRANT_RECEIPT", raising=False)
    monkeypatch.setenv("MEMBER_CONFIRM", "开始 E1 第 1 批")
    with evaluation_scope("T01"):
        scope = current_scope()
        assert scope.lane == "eval" and scope.scenario_id == "T01"
        assert scope.batch_id is None and scope.authorization_id is None


def test_real_private_receipt_is_exclusive_durable_and_parent_auditable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private-receipt.json"
    value = receipt()
    result = write_private_receipt(path, value)
    assert json.loads(path.read_text(encoding="utf-8")) == value
    assert result["path"] == str(tmp_path)
    if os.name == "nt":
        assert result["file_protection"] == "explicit-current-user-and-system-dacl"
        assert len(result["parent_acl_sha256"]) == 64
    else:
        assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_private_receipt(path, receipt() | {"batch_id": "replacement"})
    assert json.loads(path.read_text(encoding="utf-8"))["batch_id"] == value["batch_id"]


def test_missing_parent_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "receipt.json"
    with pytest.raises(OSError):
        write_private_receipt(path, receipt())
    assert not path.parent.exists()
