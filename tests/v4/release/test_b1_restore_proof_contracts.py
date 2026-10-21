"""The safe path cannot manufacture platform evidence or accept stale withdrawals."""

from __future__ import annotations

import copy
import json
import os
import py_compile
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from b1_restore_proof_support import empty_document, make_fixture, write

from tools import b1_restore_proof as proof
from tools.b1_restore_proof_contracts import (
    IMPLICIT_PG_ENV,
    LOCAL_SCHEMA,
    OWNER_ENV,
    WRITER_ENV,
    verify_monotone,
)
from tools.b1_restore_proof_process import environment, python_prefix, run_worker, worker_code
from tools.b1_restore_replay_contracts import ReplayRejected, file_hash
from tools.core_incremental_contracts import (
    EXPECTED_MANIFEST,
    TARGET,
    Request,
    UpgradeRejected,
    validate_restore,
)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    ident = "b1_restore_proof_" + uuid.uuid4().hex
    fixture = make_fixture(tmp_path, "host=127.0.0.1 port=55480 dbname=postgres user=core_test", ident, "unused")
    fixture.request.dump.write_bytes(b"synthetic-invalid-dump-never-applied")
    write(
        fixture.request.backup,
        {
            "schema": "b1-quiesced-backup-v1",
            "operation_id": "b1-proof-synthetic",
            "database": "zhiming_core_stage",
            "source_state_sha256": "e" * 64,
            "target": TARGET,
            "manifest_sha256": EXPECTED_MANIFEST,
            "mode": "0600",
            "body_free_withdrawals": True,
            "dump_sha256": file_hash(fixture.request.dump),
            "withdrawals_sha256": file_hash(fixture.request.backup_ledger),
        },
    )
    monkeypatch.setenv(OWNER_ENV, fixture.owner_dsn)
    monkeypatch.setenv(WRITER_ENV, fixture.writer_dsn)
    return fixture


def test_default_validates_pinned_inputs_without_connecting_or_running_child(inputs, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("default validation crossed physical effect boundary")

    monkeypatch.setattr(proof, "empty_target", forbidden)
    monkeypatch.setattr(proof, "restore_archive", forbidden)
    monkeypatch.setattr(proof, "run_worker", forbidden)
    assert proof.main(inputs.arguments()) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"valid": True, "apply": False, "database_connections": 0, "model_calls": 0, "external_sends": 0}


@pytest.mark.parametrize(
    "database",
    ["zhiming_core_live", "zhiming_core_stage", "core_test_main", "zhiming_core_b1_restore", "b1_restore_proof_short"],
)
def test_local_database_allowlist_cannot_target_existing_business_names(inputs, database):
    with pytest.raises(ReplayRejected, match="RESTORE_TARGET_ALLOWLIST"):
        replace(inputs.request, database=database).validate()


@pytest.mark.parametrize("field", ["dump", "backup_ledger", "ledger"])
def test_changed_bound_file_is_rejected_before_pg(inputs, field):
    path = getattr(inputs.request, field)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ReplayRejected, match="CHANGED"):
        inputs.request.validate()


@pytest.mark.parametrize("change", ["remote", "wrong_role", "wrong_database", "port", "options", "hostaddr"])
def test_dsn_privilege_identity_is_not_caller_controlled(inputs, monkeypatch, change):
    value = inputs.owner_dsn
    values = {
        "remote": value.replace("127.0.0.1", "192.0.2.1"),
        "wrong_role": value.replace(inputs.request.database + "_owner", "core_test"),
        "wrong_database": value.replace("dbname=" + inputs.request.database, "dbname=core_test_main"),
        "port": value.replace("55480", "5432"),
        "options": value + " options=-ctest=1",
        "hostaddr": value + " hostaddr=192.0.2.1",
    }
    monkeypatch.setenv(OWNER_ENV, values[change])
    with pytest.raises(ReplayRejected):
        inputs.request.dsn("owner")


def test_live_request_is_rejected_even_with_a_local_target(inputs):
    value = json.loads(inputs.request.request.read_text())
    value.update(scope="live", unit_sha256={}, skill_manifest_sha256="a" * 64)
    write(inputs.request.request, value)
    with pytest.raises((UpgradeRejected, ReplayRejected)):
        inputs.request.validate()


@pytest.mark.parametrize("name", IMPLICIT_PG_ENV)
def test_implicit_libpq_environment_is_refused_before_any_connection(inputs, monkeypatch, name):
    from tools.b1_restore_proof_pg import empty_target

    def forbidden(*args, **kwargs):
        pytest.fail("libpq was called before implicit environment rejection")

    monkeypatch.setenv(name, "synthetic-untrusted-routing-or-credential")
    monkeypatch.setattr("psycopg.connect", forbidden)
    with pytest.raises(ReplayRejected, match="IMPLICIT_PG_ENV_FORBIDDEN"):
        empty_target(inputs.request)


def test_verified_loopback_is_explicit_in_canonical_dsn_and_protected_passfile(inputs, monkeypatch):
    from psycopg.conninfo import conninfo_to_dict

    path = inputs.directory / "synthetic-pgpass"
    path.write_text("synthetic-not-a-real-password")
    monkeypatch.setenv("B1_PROOF_PGPASSFILE", str(path))
    fields = conninfo_to_dict(inputs.request.dsn("owner"))
    assert fields["hostaddr"] == "127.0.0.1" and fields["port"] == "55480"
    assert fields["passfile"] == str(path)
    env = environment(inputs.request)
    assert env["B1_PROOF_PGPASSFILE"] == str(path) and "PGPASSFILE" not in env
    monkeypatch.setenv("B1_PROOF_PGPASSFILE", path.name)
    with pytest.raises(ReplayRejected, match="ABSOLUTE_PGPASSFILE_REQUIRED"):
        inputs.request.dsn("owner")


def test_default_passfile_explicitly_uses_null_device_without_home_fallback(inputs, monkeypatch):
    from psycopg.conninfo import conninfo_to_dict

    monkeypatch.delenv("B1_PROOF_PGPASSFILE", raising=False)
    fields = conninfo_to_dict(inputs.request.dsn("owner"))
    assert fields["passfile"] == os.path.abspath(os.devnull)
    assert os.path.isabs(fields["passfile"])


@pytest.mark.parametrize("difference", ["host", "port"])
def test_owner_and_writer_must_be_the_same_server_before_any_connection(inputs, monkeypatch, difference):
    from tools.b1_restore_proof_pg import empty_target

    def forbidden(*args, **kwargs):
        pytest.fail("cross-server identity reached libpq before rejection")

    value = (
        inputs.writer_dsn.replace("127.0.0.1", "::1")
        if difference == "host"
        else inputs.writer_dsn.replace("55480", "55481")
    )
    monkeypatch.setenv(WRITER_ENV, value)
    monkeypatch.setattr("psycopg.connect", forbidden)
    with pytest.raises(ReplayRejected, match="SAME_RESTORE_SERVER_REQUIRED"):
        empty_target(inputs.request)


def test_formal_receipt_is_self_checked_by_actual_consumer_before_return(inputs):
    upgrade, backup, _ = inputs.request.validate()
    local = {"schema": LOCAL_SCHEMA, "admissible": False}
    assert proof.validate_generated(upgrade, backup, local, local=True) == local
    with pytest.raises(UpgradeRejected, match="RESTORE_PROOF_SCHEMA"):
        proof.validate_generated(upgrade, backup, local, local=False)


def test_formal_platform_is_observed_and_local_schema_cannot_unlock_validator(inputs, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    with pytest.raises(ReplayRejected, match="LINUX_PROOF_REQUIRED"):
        replace(inputs.request, local_drill=False).platform()
    upgrade, backup, _ = inputs.request.validate()
    with pytest.raises(UpgradeRejected, match="RESTORE_PROOF_SCHEMA"):
        validate_restore(upgrade, backup, {"schema": LOCAL_SCHEMA, "admissible": False})


def test_formal_source_and_python_require_the_fixed_release_and_lexical_venv(inputs):
    upgrade = Request.parse(json.loads(inputs.request.request.read_text()))
    formal = replace(inputs.request, local_drill=False)
    with pytest.raises(ReplayRejected, match="FORMAL_FIXED_RELEASE_REQUIRED"):
        formal.formal_paths(upgrade)
    root = Path(upgrade.release)
    formal = replace(formal, candidate_source=root)
    with pytest.raises(ReplayRejected, match="FORMAL_FIXED_VENV_REQUIRED"):
        formal.formal_paths(upgrade)
    formal = replace(formal, candidate_python=root / "venv/core/bin/python")
    formal.formal_paths(upgrade)
    with pytest.raises(ReplayRejected, match="FORMAL_FIXED_VENV_REQUIRED"):
        replace(formal, candidate_python=Path("/usr/bin/python3")).formal_paths(upgrade)


@pytest.mark.parametrize("kind", ["revocation", "draw", "tarot", "receipt", "owners"])
def test_new_ledger_must_retain_all_old_safety_evidence(kind):
    old = empty_document()
    if kind == "revocation":
        old["owners"][0]["revocations"].append(
            {"kind": "message", "entity_id": "synthetic", "operation": "deleted", "metadata": {}}
        )
    if kind in {"draw", "tarot"}:
        old["deleted_draws" if kind == "draw" else "tarot_requests"].append({"synthetic": "tombstone"})
    if kind == "receipt":
        old["delivery_receipts"].append(
            {
                "owner": "primary",
                "business_id": "synthetic",
                "channel": "feishu",
                "target": "synthetic",
                "attempts": 1,
                "status": "sent",
                "receipt": "receipt",
            }
        )
    new = empty_document()
    if kind == "owners":
        new["owners"].pop()
    with pytest.raises(ReplayRejected, match="STALE|OWNER"):
        verify_monotone(old, new)


def test_sent_receipt_cannot_downgrade_or_change_but_uncertain_can_upgrade():
    old = empty_document()
    old["delivery_receipts"] = [
        {
            "owner": "primary",
            "business_id": "synthetic",
            "channel": "feishu",
            "target": "synthetic",
            "attempts": 1,
            "status": "uncertain",
            "receipt": "",
        }
    ]
    new = copy.deepcopy(old)
    new["delivery_receipts"][0].update(status="sent", receipt="synthetic-receipt", attempts=2)
    verify_monotone(old, new)
    with pytest.raises(ReplayRejected, match="STALE_RECEIPTS"):
        verify_monotone(new, old)


def test_child_environment_clears_credentials_tracing_and_does_not_embed_dsn_in_code(inputs, monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-key-must-not-propagate")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-trace-key")
    env = environment(inputs.request)
    assert "KIMI_API_KEY" not in env and "LANGSMITH_API_KEY" not in env
    assert env["LANGSMITH_TRACING"] == "false" and env["OTEL_SDK_DISABLED"] == "true"
    code = worker_code(inputs.request, "replay")
    assert inputs.owner_dsn not in code and inputs.writer_dsn not in code


def test_output_requires_new_path_and_formal_private_directory(inputs):
    path = inputs.directory / "receipt.json"
    path.write_text("existing")
    with pytest.raises(ReplayRejected, match="NEW_PROOF_OUTPUT_REQUIRED"):
        proof.output_preflight(path, local=True)
    assert path.read_text() == "existing"
    if os.name == "posix":
        inputs.directory.chmod(0o755)
        with pytest.raises(ReplayRejected, match="PRIVATE_PROOF_DIRECTORY"):
            proof.output_preflight(inputs.directory / "new.json", local=False)


def test_real_timestamp_valid_poisoned_bytecode_is_ignored_without_changing_cache(tmp_path):
    module = tmp_path / "synthetic_cache_proof.py"
    poison, source = "VALUE='poison'\n", "VALUE='source'\n"
    assert len(poison) == len(source)
    module.write_text(poison, encoding="utf-8")
    stamp = module.stat()
    cache = tmp_path / "__pycache__" / ("synthetic_cache_proof." + sys.implementation.cache_tag + ".pyc")
    py_compile.compile(
        str(module),
        cfile=str(cache),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    original_cache = cache.read_bytes()
    module.write_text(source, encoding="utf-8")
    os.utime(module, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    code = f"import sys;sys.path.insert(0,{str(tmp_path)!r});import synthetic_cache_proof as m;print(m.VALUE)"
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    ordinary = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code], env=env, capture_output=True, text=True, check=True
    )
    guarded = subprocess.run(
        [*python_prefix(Path(sys.executable)), "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert ordinary.stdout.strip() == "poison" and guarded.stdout.strip() == "source"
    assert cache.read_bytes() == original_cache and module.read_text() == source


def test_pinned_worker_argv_forces_nonexistent_cache_prefix_and_filters_environment(inputs, monkeypatch):
    called = []

    def observe(arguments, **kwargs):
        called.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, '{"synthetic":"argv-only"}', "")

    monkeypatch.setenv("PYTHONPYCACHEPREFIX", "synthetic-inherited-prefix-forbidden")
    monkeypatch.setattr("tools.b1_restore_proof_process.subprocess.run", observe)
    assert run_worker(inputs.request, "replay", empty_document()) == {"synthetic": "argv-only"}
    args, options = called[0]
    assert args[:5] == python_prefix(inputs.request.candidate_python)
    assert args[5] == "-c" and "PYTHONPYCACHEPREFIX" not in options["env"]
    assert args[4] == "pycache_prefix=" + os.path.abspath(os.devnull)
