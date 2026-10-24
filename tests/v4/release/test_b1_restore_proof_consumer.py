"""Reject wrong-source restore receipts without any Native/PG effects."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools import core_incremental as controller
from tools.core_incremental_contracts import (
    EXPECTED_MANIFEST,
    MIGRATIONS,
    PREVIOUS,
    STAGE_UNITS,
    TARGET,
    Request,
    UpgradeRejected,
    digest,
    validate_restore,
)

# Actual Windows PG15 body-free receipt, observed 2026-10-21 08:56:09+08.
# Raw private source: 4085 bytes, SHA256 c34655231814091bb1e35a2f36c5dea766756244efd97d36d926821d1bf503a1.
# This final five-probe local receipt is deliberately non-admissible.
OBSERVED_LOCAL = json.loads(r"""{
  "actual_pg_restore": true,
  "admissible": false,
  "backup_sha256": "ca5da9f9e729e5a46d78b38c624d8be75ffd655b6c142f9b14b8b003bcf71cd9",
  "candidate_python_sha256": "f38084ff0b75c199883d4369bce0d142e08ade5e3b66a0a7f42085599468b751",
  "checksums": {
    "1": "0015f6b2a9d655b5d47774a7fc44456a299953db1b0b05fcd13558206f855586",
    "2": "a7df7398ce522df386dbefcf464b7d0b550fabd558e47adec6fd991c15715f67",
    "3": "9905263b6a5bb7eabd133607b587efc055c475ea6017c497116be02df6d32ff5",
    "4": "eb6f19a7753168387388cff5d001694f90676dcbc60a72c5d7de8ccb76f27145",
    "5": "19182ec61c19d9ff3472a867b9b2ce41fa60fe22579e83dd04b4a50308708e62",
    "6": "c3469b6bad49358c11562ec16c70f840d5a0d50a8c9041c2f044a888aa644ee2",
    "7": "6c6c544a9b3def93da445ff5a58338e242c096294627dd7414c139263e3083ce"
  },
  "created_at": "2026-10-21T08:56:09.488519+08:00",
  "database": "b1_restore_proof_32b8cc3be7b54884951b864747f6aae2",
  "database_creation_observed": false,
  "dump_sha256": "cf5da8ea642acc73aa867af9adc09f0254f2b2543cdf35a369be18c422d8a0a7",
  "empty_target_observed": {
    "database": "b1_restore_proof_32b8cc3be7b54884951b864747f6aae2",
    "host": "127.0.0.1",
    "port": 55480,
    "role": "b1_restore_proof_32b8cc3be7b54884951b864747f6aae2_owner",
    "version_num": 150019
  },
  "external_sends": 0,
  "generator_sha256": "e2b840274433b205bdc1d8833b64aa587548817ea0bda6ff0b5351c2123d2283",
  "latest_ledger_sha256": "b5c26fdba66cbac34e1a3cf3fa50ac7d37911d5addc7f4e41d193bc6441869c7",
  "latest_withdrawals_replayed": true,
  "manifest_sha256": "49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c",
  "migration": {
    "checksums": {
      "1": "0015f6b2a9d655b5d47774a7fc44456a299953db1b0b05fcd13558206f855586",
      "2": "a7df7398ce522df386dbefcf464b7d0b550fabd558e47adec6fd991c15715f67",
      "3": "9905263b6a5bb7eabd133607b587efc055c475ea6017c497116be02df6d32ff5",
      "4": "eb6f19a7753168387388cff5d001694f90676dcbc60a72c5d7de8ccb76f27145",
      "5": "19182ec61c19d9ff3472a867b9b2ce41fa60fe22579e83dd04b4a50308708e62",
      "6": "c3469b6bad49358c11562ec16c70f840d5a0d50a8c9041c2f044a888aa644ee2",
      "7": "6c6c544a9b3def93da445ff5a58338e242c096294627dd7414c139263e3083ce"
    },
    "forward_migrations": [
      5,
      6,
      7
    ]
  },
  "model_calls": 0,
  "operation_id": "b1-proof-synthetic",
  "pg_restore": {
    "executable_sha256": "569f7a2700e2760f3a7294b77c4cff64bd3483f34889afe550b514c51fef7e72",
    "executed": true,
    "exit_code": 0
  },
  "platform": "win32",
  "posix_permissions_verified": false,
  "replay_first": {
    "changed": true,
    "checkpoint_ranges_checked": 3,
    "counts": {
      "deleted_draws": 1,
      "external_sends": 0,
      "model_calls": 0,
      "owners": 2,
      "protected_receipts": 2,
      "tarot_tombstones": 1
    },
    "deleted_draws_checked": 0,
    "state_after_sha256": "2ffdc6388c68ed273936196c91bc1411f9c866fb18cdd2b8d3ab3d60b7a650ae",
    "state_before_sha256": "0455eef851cf7307d23b70d8ef2811afa84c7d56886a98f11c65909c883178d4",
    "whole_revocations_checked": 2
  },
  "replay_second": {
    "changed": false,
    "checkpoint_ranges_checked": 3,
    "counts": {
      "deleted_draws": 0,
      "external_sends": 0,
      "model_calls": 0,
      "owners": 2,
      "protected_receipts": 1,
      "tarot_tombstones": 1
    },
    "deleted_draws_checked": 0,
    "state_after_sha256": "2ffdc6388c68ed273936196c91bc1411f9c866fb18cdd2b8d3ab3d60b7a650ae",
    "state_before_sha256": "2ffdc6388c68ed273936196c91bc1411f9c866fb18cdd2b8d3ab3d60b7a650ae",
    "whole_revocations_checked": 2
  },
  "restored_schema4": {
    "checksums": {
      "1": "0015f6b2a9d655b5d47774a7fc44456a299953db1b0b05fcd13558206f855586",
      "2": "a7df7398ce522df386dbefcf464b7d0b550fabd558e47adec6fd991c15715f67",
      "3": "9905263b6a5bb7eabd133607b587efc055c475ea6017c497116be02df6d32ff5",
      "4": "eb6f19a7753168387388cff5d001694f90676dcbc60a72c5d7de8ccb76f27145"
    },
    "state_sha256": "580e7f386fa3e1c384aef4ae96d02ecc19cd9307872183c10f10214f5da1fca7"
  },
  "runtime_safe": true,
  "schema": "b1-local-restore-drill-v1",
  "sent_uncertain_protected": true,
  "target": "b9a89b6f84f7bebb640de080548010859aae630c",
  "writer_permissions": {
    "forbidden_probes_denied": 5,
    "identity": {
      "database": "b1_restore_proof_32b8cc3be7b54884951b864747f6aae2",
      "host": "127.0.0.1",
      "port": 55480,
      "role": "b1_restore_proof_32b8cc3be7b54884951b864747f6aae2_writer",
      "version_num": 150019
    },
    "tables_checked": 24
  }
}""")
H = "a" * 64
NOW = datetime(2026, 10, 21, 1, tzinfo=UTC)
Values = tuple[dict[str, Any], Request, dict[str, Any], dict[str, Any]]


@pytest.fixture
def values() -> Values:
    raw = {
        "schema": "b1-incremental-request-v1",
        "operation_id": OBSERVED_LOCAL["operation_id"],
        "scope": "stage",
        "target": TARGET,
        "previous": PREVIOUS,
        "hostname": "synthetic-host",
        "manifest_sha256": EXPECTED_MANIFEST,
        "controller_sha256": H,
        "owners": ["primary"],
        "minimum_free_bytes": 8 * 1024**3,
        "unit_sha256": dict.fromkeys(STAGE_UNITS, H),
        "skill_manifest_sha256": "",
    }
    request = Request.parse(raw)
    backup = {
        "schema": "b1-quiesced-backup-v1",
        "operation_id": request.operation_id,
        "database": request.database,
        "source_state_sha256": OBSERVED_LOCAL["restored_schema4"]["state_sha256"],
        "target": TARGET,
        "manifest_sha256": EXPECTED_MANIFEST,
        "mode": "0600",
        "body_free_withdrawals": True,
        "dump_sha256": OBSERVED_LOCAL["dump_sha256"],
        "withdrawals_sha256": H,
    }
    # Explicitly synthetic formal shape; this transformation is never a Linux proof.
    proof = copy.deepcopy(OBSERVED_LOCAL)
    proof.update(
        schema="b1-isolated-restore-proof-v1",
        database=request.restore_database,
        platform="linux",
        admissible=True,
        posix_permissions_verified=True,
        backup_sha256=digest(backup),
    )
    for row, role in (
        (proof["empty_target_observed"], "owner"),
        (proof["writer_permissions"]["identity"], "writer"),
    ):
        row.update(
            database=request.restore_database,
            role=request.restore_database + "_" + role,
            port=5432,
        )
    proof["writer_permissions"]["forbidden_probes_denied"] = 5
    return raw, request, backup, proof


def set_field(value: dict[str, Any], path: str, replacement: object) -> None:
    parts = path.split(".")
    for key in parts[:-1]:
        value = value[key]
    value[parts[-1]] = replacement


def test_complete_synthetic_formal_shape_is_consistent_but_does_not_run_anything(
    values: Values, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("contract validation crossed physical boundary")

    monkeypatch.setattr("psycopg.connect", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    _, request, backup, proof = values
    validate_restore(request, backup, proof)


def test_actual_windows_receipt_only_relabelled_schema_and_database_is_rejected(values: Values) -> None:
    _, request, backup, _ = values
    proof = copy.deepcopy(OBSERVED_LOCAL)
    proof.update(schema="b1-isolated-restore-proof-v1", database=request.restore_database)
    assert proof["platform"] == "win32"
    assert proof["admissible"] is False and proof["posix_permissions_verified"] is False
    with pytest.raises(UpgradeRejected, match="RESTORE_PROOF_ORIGIN"):
        validate_restore(request, backup, proof)


@pytest.mark.parametrize(
    ("path", "replacement", "code"),
    [
        ("platform", "win32", "ORIGIN"),
        ("admissible", False, "ORIGIN"),
        ("admissible", 1, "ORIGIN"),
        ("posix_permissions_verified", False, "ORIGIN"),
        ("operation_id", "different-operation", "OPERATION"),
        ("dump_sha256", "f" * 64, "DUMP_BINDING"),
        ("generator_sha256", "not-a-hash", "OBSERVATION_HASH"),
        ("candidate_python_sha256", None, "OBSERVATION_HASH"),
        ("latest_ledger_sha256", "", "OBSERVATION_HASH"),
        ("empty_target_observed", None, "OBSERVATION_MISSING"),
        ("empty_target_observed.database", "zhiming_core_stage", "IDENTITY"),
        ("empty_target_observed.role", "postgres", "IDENTITY"),
        ("empty_target_observed.host", "192.0.2.1", "SERVER"),
        ("empty_target_observed.host", [], "SERVER"),
        ("empty_target_observed.port", 55480, "SERVER"),
        ("empty_target_observed.port", True, "SERVER"),
        ("empty_target_observed.version_num", 160000, "SERVER"),
        ("restored_schema4.state_sha256", "f" * 64, "SCHEMA4_BINDING"),
        ("restored_schema4.checksums", MIGRATIONS, "SCHEMA4_BINDING"),
        ("pg_restore.executed", False, "ARCHIVE_NOT_EXECUTED"),
        ("pg_restore.exit_code", False, "ARCHIVE_NOT_EXECUTED"),
        ("pg_restore.exit_code", 1, "ARCHIVE_NOT_EXECUTED"),
        ("migration.forward_migrations", [5, 6, 7, 8], "MIGRATION_OBSERVATION"),
        ("migration.checksums", {}, "MIGRATION_OBSERVATION"),
        ("replay_first.changed", False, "REPLAY_CHANGED"),
        ("replay_first.counts.model_calls", 1, "EXTERNAL_EFFECT"),
        ("replay_second.counts.external_sends", True, "EXTERNAL_EFFECT"),
        ("replay_second.counts.owners", 0, "REPLAY_OWNERS"),
        ("replay_second.whole_revocations_checked", -1, "REPLAY_COUNTS"),
        ("replay_second.state_before_sha256", "bad", "OBSERVATION_HASH"),
        ("writer_permissions.identity.role", "postgres", "IDENTITY"),
        ("writer_permissions.identity.port", 55480, "SERVER"),
        ("writer_permissions.identity.version_num", 150018, "SERVER"),
        ("writer_permissions.forbidden_probes_denied", 4, "PERMISSION_OBSERVATION"),
        ("writer_permissions.tables_checked", 4, "PERMISSION_OBSERVATION"),
    ],
)
def test_each_observation_binding_fails_closed(values: Values, path: str, replacement: object, code: str) -> None:
    _, request, backup, proof = values
    set_field(proof, path, replacement)
    with pytest.raises(UpgradeRejected, match=code):
        validate_restore(request, backup, proof)


def test_second_replay_changed_or_disconnected_state_is_rejected(values: Values) -> None:
    _, request, backup, proof = values
    proof["replay_second"].update(changed=True, state_after_sha256="f" * 64)
    with pytest.raises(UpgradeRejected, match="REPLAY_NOT_IDEMPOTENT"):
        validate_restore(request, backup, proof)
    proof["replay_second"].update(changed=False, state_before_sha256="f" * 64)
    with pytest.raises(UpgradeRejected, match="REPLAY_NOT_IDEMPOTENT"):
        validate_restore(request, backup, proof)


def test_four_result_flags_without_the_observation_chain_cannot_pass(values: Values) -> None:
    _, request, backup, proof = values
    for key in (
        "empty_target_observed",
        "restored_schema4",
        "migration",
        "pg_restore",
        "replay_first",
        "replay_second",
    ):
        proof.pop(key)
    with pytest.raises(UpgradeRejected, match="RESTORE_OBSERVATION_MISSING"):
        validate_restore(request, backup, proof)


@pytest.mark.parametrize("action", ["migrate", "backfill"])
@pytest.mark.parametrize("invalid", ["actual_local", "origin", "nested", "approval", "missing"])
def test_native_static_preflight_rejects_before_native_construction(
    values: Values, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, invalid: str
) -> None:
    raw, _, backup, proof = values
    config: dict[str, Any] = {}
    raw["host_config_sha256"] = digest(config)
    if invalid == "actual_local":
        proof = copy.deepcopy(OBSERVED_LOCAL)
        proof.update(schema="b1-isolated-restore-proof-v1", database=values[1].restore_database)
    if invalid == "origin":
        proof.update(platform="win32", admissible=False, posix_permissions_verified=False)
    if invalid == "nested":
        proof["writer_permissions"]["identity"]["database"] = "zhiming_core_live"
    approval = {
        "schema": "b1-incremental-approval-v1",
        "operation_id": raw["operation_id"],
        "scope": raw["scope"],
        "request_sha256": digest(raw),
        "controller_sha256": H,
        "expires_at": "2026-10-21T02:00:00+00:00",
        "quiesced_upgrade": True,
        "resume_business": False,
        "model_calls": False,
        "channel_sends": False,
        "restore_sha256": "f" * 64 if invalid == "approval" else digest(proof),
    }
    args = argparse.Namespace(native=True, action=action, output=tmp_path / "never-created.json")
    for name, document in (
        ("approval", approval),
        ("host_config", config),
        ("backup", backup),
        ("restore", proof),
        ("migration", None),
        ("review", None),
    ):
        path = tmp_path / (name + ".json")
        if document is not None:
            path.write_text(json.dumps(document), encoding="utf-8")
        setattr(args, name, path if document is not None else None)
    if invalid == "missing":
        args.restore = None
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("physical")
        pytest.fail("invalid proof reached Native/PG")

    monkeypatch.setattr(controller, "controller_digest", lambda: H)
    monkeypatch.setattr(
        "mingjing_core.timekit.clock.get_clock",
        lambda: SimpleNamespace(now=lambda: NOW),
    )
    monkeypatch.setattr("tools.core_incremental_files.regular", lambda *args, **kwargs: None)
    monkeypatch.setattr("tools.core_incremental_host.NativePort", forbidden)
    monkeypatch.setattr("psycopg.connect", forbidden)
    with pytest.raises(UpgradeRejected):
        controller.native_apply(args, raw)
    assert calls == [] and not args.output.exists()
