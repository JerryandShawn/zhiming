"""Current core-only reviewed pins cannot grant restore or publication authority."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import FrozenInstanceError, replace

import psycopg
import pytest
from first_release_support import contract_document, environment, packed_source, pin_document, repin, write_json
from psycopg.conninfo import conninfo_to_dict

from tools.first_release_contracts import ReleasePin, RestoreRejected
from tools.first_release_restore import main, validate_inputs


@pytest.fixture(name="tmp_path")
def short_workspace(tmp_path_factory):
    # The nested immutable release layout exceeds MAX_PATH under pytest's full test-name directory.
    return tmp_path_factory.mktemp("fr")


def test_reviewed_source_and_three_locks_validate_without_database_or_mutations(tmp_path, monkeypatch, capsys):
    pin, contract = packed_source(tmp_path)
    write_json(tmp_path / "pin.json", pin_document(pin))
    write_json(tmp_path / "contract.json", contract_document(contract))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("validation must not connect to a database")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.chdir(tmp_path)
    assert main(["--pin", str(tmp_path / "pin.json"), "--contract", str(tmp_path / "contract.json")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["database_connections"] == result["mutations"] == 0
    assert result["profile"] == "core-only-1-8-v1" and len(result["migrations"]) == 8
    assert len(result["locks"]) == 3
    assert result["runtime_verified"] is result["linux_attestation"] is result["native_restore_completed"] is False
    assert result["publication"] is False and "admissible" not in result
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    with pytest.raises(FrozenInstanceError):
        pin.candidate = "b" * 40


@pytest.mark.parametrize("name", ["requirements-core.lock", "requirements-charts.lock", "k3-tokenizer.lock.json"])
def test_lock_change_cannot_be_hidden_by_repacking_without_new_review(tmp_path, name):
    pin, contract = packed_source(tmp_path)
    path = contract.candidate_source / name
    path.write_bytes(path.read_bytes() + b"\n")
    changed = repin(contract.candidate_source)
    reviewed = replace(changed, locks=pin.locks)
    with pytest.raises(RestoreRejected, match="REVIEWED_LOCK_CHANGED"):
        validate_inputs(reviewed, contract, workspace=tmp_path)


@pytest.mark.parametrize("kind", ["missing", "changed", "duplicate", "0009"])
def test_core_only_profile_rejects_missing_rewritten_duplicate_or_p5_migration(tmp_path, kind):
    _, contract = packed_source(tmp_path)
    directory = contract.candidate_source / "mingjing_core/repositories/migrations"
    path = next(directory.glob("0008_*.sql"))
    if kind == "missing":
        path.unlink()
    elif kind == "changed":
        path.write_bytes(path.read_bytes() + b"\n-- synthetic changed migration\n")
    elif kind == "duplicate":
        (directory / "0008_duplicate.sql").write_bytes(path.read_bytes())
    else:
        (directory / "0009_reserved_p5.sql").write_text("-- synthetic P5 requires a different reviewed profile\n")
    changed = repin(contract.candidate_source)
    with pytest.raises(RestoreRejected, match="MIGRATION"):
        validate_inputs(changed, contract, workspace=tmp_path)


@pytest.mark.parametrize("kind", ["candidate", "blob", "body", "extra", "path", "manifest"])
def test_source_identity_and_exact_members_cannot_be_self_attested(tmp_path, kind):
    pin, contract = packed_source(tmp_path)
    root = contract.candidate_source
    manifest = root / "__release_manifest__.json"
    data = json.loads(manifest.read_text())
    if kind == "candidate":
        pin = replace(pin, candidate="b" * 40)
    elif kind == "blob":
        next(iter(data["files"].values()))["git_blob_sha1"] = "0" * 40
        write_json(manifest, data)
        import hashlib

        pin = replace(pin, manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    elif kind == "body":
        (root / "requirements-core.lock").write_text("synthetic changed content")
    elif kind == "extra":
        (root / "extra.py").write_text("SYNTHETIC = True")
    elif kind == "path":
        contract = replace(contract, candidate_source=root.parent / ".." / root.parent.name / root.name)
    else:
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(RestoreRejected):
        validate_inputs(pin, contract, workspace=tmp_path)


def test_source_symlink_is_rejected_even_when_target_bytes_match(tmp_path):
    pin, contract = packed_source(tmp_path)
    if os.name == "nt":
        # NTFS junctions exercise a real reparse point without granting symlink privileges to the test process.
        link = contract.candidate_source / "mingjing_core/repositories/migrations"
        target = tmp_path / "outside-migrations"
        assert target.is_relative_to(tmp_path) and link.is_relative_to(tmp_path)
        link.rename(target)
        command = "New-Item -ItemType Junction -Path '{}' -Target '{}' | Out-Null".format(
            str(link).replace("'", "''"), str(target).replace("'", "''")
        )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, timeout=20)
        assert result.returncode == 0, "actual local NTFS junction required; private diagnostic withheld"
        try:
            with pytest.raises(RestoreRejected, match="LINKED_PATH"):
                validate_inputs(pin, contract, workspace=tmp_path)
        finally:
            link.rmdir()
        return
    path = contract.candidate_source / "requirements-core.lock"
    target = tmp_path / "outside.lock"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(RestoreRejected, match="LINKED_PATH"):
        validate_inputs(pin, contract, workspace=tmp_path)


@pytest.mark.parametrize("database", ["zhiming_core_live", "zhiming_core_stage", "zhiming_core_b1_restore", "postgres"])
def test_existing_application_or_generic_database_is_out_of_scope(tmp_path, database):
    pin, contract = packed_source(tmp_path)
    with pytest.raises(RestoreRejected, match="NEW_DATABASE_ONLY"):
        validate_inputs(pin, replace(contract, database=database), workspace=tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "203.0.113.10"),
        ("host", "localhost"),
        ("hostaddr", "203.0.113.10"),
        ("port", "5432"),
        ("options", "-c role=postgres"),
        ("service", "synthetic"),
        ("passfile", "synthetic-private-file"),
        ("user", "postgres"),
        ("dbname", "zhiming_core_live"),
    ],
)
def test_explicit_dsn_rejects_remote_redirects_role_or_database_changes(tmp_path, field, value):
    _, contract = packed_source(tmp_path)
    configured = environment(contract)
    fields = conninfo_to_dict(configured["FIRST_RELEASE_WRITER_DSN"])
    fields[field] = value
    from psycopg.conninfo import make_conninfo

    configured["FIRST_RELEASE_WRITER_DSN"] = make_conninfo(**fields)
    with pytest.raises(RestoreRejected):
        contract.dsns(configured)


def test_implicit_pg_and_cross_location_and_non_boolean_local_mode_fail_closed(tmp_path):
    pin, contract = packed_source(tmp_path)
    configured = environment(contract)
    with pytest.raises(RestoreRejected, match="IMPLICIT_PG"):
        contract.dsns({**configured, "PGPASSWORD": "SYNTHETIC_PRIVATE_SECRET"})
    configured["FIRST_RELEASE_WRITER_DSN"] = configured["FIRST_RELEASE_WRITER_DSN"].replace("55480", "55481")
    with pytest.raises(RestoreRejected, match="OWNER_WRITER_LOCATION"):
        contract.dsns(configured)
    with pytest.raises(RestoreRejected, match="LOCAL_MODE_TYPE"):
        validate_inputs(pin, replace(contract, local_drill=1), workspace=tmp_path)


def test_no_apply_command_and_no_self_attested_success_field(tmp_path, capsys):
    pin, _ = packed_source(tmp_path)
    assert main(["--apply", "SYNTHETIC_PRIVATE_SECRET"]) == 2
    assert "SYNTHETIC_PRIVATE_SECRET" not in capsys.readouterr().out
    with pytest.raises(RestoreRejected, match="RELEASE_PIN_FIELDS"):
        ReleasePin.parse({**pin_document(pin), "admissible": True})


def test_actual_process_pgoptions_cannot_be_hidden_by_clean_explicit_environment(tmp_path, monkeypatch):
    from tools.first_release_acl import verify_database_acl

    pin, contract = packed_source(tmp_path)
    monkeypatch.setenv("PGOPTIONS", "-c role=SYNTHETIC_PRIVATE_SECRET")

    def forbidden(*args, **kwargs):
        pytest.fail("ambient libpq options must be rejected before connecting")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    with pytest.raises(RestoreRejected, match="IMPLICIT_PG_REJECTED"):
        verify_database_acl(contract, pin, environment=environment(contract))
