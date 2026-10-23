"""Pure target/file contracts; these checks do not count as Linux or PG evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tools.b1_restore_replay_contracts import (
    ReplayRejected,
    RestoreRequest,
    load_document,
    verify_members,
)


@pytest.fixture
def restore_request(tmp_path: Path) -> RestoreRequest:
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "schema": "core3-withdrawals-v2",
                "owners": [],
                "tarot_requests": [],
                "deleted_draws": [],
                "delivery_receipts": [],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return RestoreRequest(
        "b1-replay-contract",
        "stage",
        "zhiming_core_b1_restore",
        "mingjing_core",
        tmp_path,
        Path(sys.executable).resolve(),
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        True,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "live"),
        ("scope", "live_restore"),
        ("database", "zhiming_core_live"),
        ("database", "zhiming_core_stage"),
        ("schema", "public"),
        ("operation_id", "short"),
        ("operation_id", "bad/private operation"),
        ("ledger_sha256", "0" * 63),
    ],
)
def test_only_explicit_stage_restore_target_is_valid(restore_request: RestoreRequest, field: str, value: str) -> None:
    with pytest.raises(ReplayRejected):
        replace(restore_request, **{field: value}).validate()


@pytest.mark.parametrize(
    "dsn",
    [
        "host=server.example dbname=zhiming_core_b1_restore user=zhiming_core_b1_restore_owner",
        "host=127.0.0.1 dbname=zhiming_core_live user=zhiming_core_b1_restore_owner",
        "host=127.0.0.1 dbname=zhiming_core_b1_restore user=postgres",
        "host=127.0.0.1 port=5433 dbname=zhiming_core_b1_restore user=zhiming_core_b1_restore_owner",
        "host=127.0.0.1 hostaddr=203.0.113.1 dbname=zhiming_core_b1_restore user=zhiming_core_b1_restore_owner",
        "host=127.0.0.1 options=-csearch_path=public dbname=zhiming_core_b1_restore user=zhiming_core_b1_restore_owner",
    ],
)
def test_dsn_rejects_remote_wrong_identity_and_hidden_overrides(
    restore_request: RestoreRequest,
    monkeypatch: pytest.MonkeyPatch,
    dsn: str,
) -> None:
    monkeypatch.setenv("B1_RESTORE_OWNER_DSN", dsn)
    with pytest.raises(ReplayRejected):
        restore_request.dsn()


def test_local_drill_does_not_expand_stage_ports(
    restore_request: RestoreRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "B1_RESTORE_OWNER_DSN",
        "host=127.0.0.1 port=55481 dbname=zhiming_core_b1_restore user=zhiming_core_b1_restore_owner",
    )
    assert restore_request.dsn()
    with pytest.raises(ReplayRejected, match="RESTORE_PORT"):
        replace(restore_request, local_drill=False).dsn()


def test_ledger_change_and_private_body_fields_reject(
    restore_request: RestoreRequest,
) -> None:
    restore_request.validate()
    assert load_document(restore_request)["owners"] == []
    document = json.loads(restore_request.ledger.read_text())
    document["owners"] = [
        {
            "schema_version": "core3.0",
            "owner_user_id": "synthetic",
            "revocations": [
                {
                    "kind": "fact",
                    "entity_id": "synthetic",
                    "operation": "deleted",
                    "metadata": {"quote": "synthetic private text"},
                }
            ],
        }
    ]
    restore_request.ledger.write_text(json.dumps(document))
    with pytest.raises(ReplayRejected, match="LEDGER_CHANGED"):
        restore_request.validate()
    updated = replace(
        restore_request,
        ledger_sha256=hashlib.sha256(restore_request.ledger.read_bytes()).hexdigest(),
    )
    with pytest.raises(ReplayRejected, match="REVOCATION_BODY_FORBIDDEN"):
        load_document(updated)


def test_unmanifested_candidate_code_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "unapproved.py").write_text("raise RuntimeError('unapproved')")
    with pytest.raises(ReplayRejected, match="UNEXPECTED_CANDIDATE_FILE"):
        verify_members(tmp_path, set())
