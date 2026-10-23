"""Full canonical candidate files, an actual isolated Python, and a real fresh PG target."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import replace
from pathlib import Path, PurePosixPath

import psycopg
import pytest
from first_release_support import ROOT, repin, write_json
from test_first_release_local_restore_pg import sample as sample
from test_first_release_replay_idempotence_pg import complete_state

from mingjing_core.repositories.postgres import PostgresRepository
from tools import first_release_candidate_process as process
from tools import first_release_local_restore as restore
from tools import first_release_local_upgrade as upgrade
from tools.deploy_core import export_withdrawals
from tools.first_release_candidate_process import CandidatePreflight
from tools.first_release_contracts import RestoreRejected
from tools.first_release_local_inputs import file_hash


@pytest.fixture(scope="module")
def canonical_source():
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    head = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, env=environment, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    archive = subprocess.run(
        ["git", "archive", "--format=tar", head], cwd=ROOT, env=environment, capture_output=True, check=True
    ).stdout
    return head, archive


def unpack(root, archive):
    with tarfile.open(fileobj=io.BytesIO(archive)) as members:
        for member in members:
            name = PurePosixPath(member.name)
            assert not name.is_absolute() and ".." not in name.parts and "\\" not in member.name
            path = root.joinpath(*name.parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                assert member.isfile(), "CANONICAL_ORDINARY_SOURCE_REQUIRED"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(members.extractfile(member).read())


@pytest.fixture
def candidate(sample, canonical_source):
    with tempfile.TemporaryDirectory(prefix="frcp-") as folder:
        workspace = Path(folder)
        head, archive = canonical_source
        root = workspace / "private" / ("first-release-" + sample.inputs.contract.operation_id[3:]) / head
        unpack(root, archive)
        pin = repin(root)
        contract = replace(sample.inputs.contract, candidate_source=root)
        dump = root.parent / "backup.dump"
        dump.write_bytes(sample.inputs.dump.read_bytes())
        sample.inputs = replace(
            sample.inputs,
            release=pin,
            contract=contract,
            workspace=workspace,
            dump=dump,
            dump_pin=replace(sample.inputs.dump_pin, candidate=head, manifest_sha256=pin.manifest_sha256),
        )
        repo = PostgresRepository(sample.source, initialize=False, max_size=1)
        try:
            document = export_withdrawals(repo)
        finally:
            repo.close()
        ledger = root.parent / "latest-withdrawals.json"
        write_json(ledger, document)
        configured = os.environ.get("FIRST_RELEASE_CANDIDATE_TEST_PYTHON")
        fallback = ROOT.parent / "zhiming-v4/.venv-k3/Scripts/python.exe" if os.name == "nt" else Path(sys.executable)
        python = Path(configured) if configured else fallback
        assert python.is_file(), "EXPLICIT_REAL_CORE_LOCKED_VENV_REQUIRED"
        request = CandidatePreflight.parse(
            python,
            ledger,
            {
                "schema": "first-release-local-preflight-pin-v1",
                "candidate": pin.candidate,
                "manifest_sha256": pin.manifest_sha256,
                "dump_sha256": sample.inputs.dump_pin.dump_sha256,
                "ledger_sha256": file_hash(ledger),
                "python_sha256": file_hash(python),
                "worker_sha256": file_hash(process.WORKER),
            },
        )
        yield sample, request


def observe(monkeypatch, snapshots):
    original = process.candidate_preflight

    def observed(request, inputs, dsns, creator):
        repo = PostgresRepository(dsns["owner"], initialize=False, max_size=1)
        try:
            snapshots.append(complete_state(repo))
            try:
                return original(request, inputs, dsns, creator)
            finally:
                snapshots.append(complete_state(repo))
        finally:
            repo.close()

    monkeypatch.setattr(process, "candidate_preflight", observed)


def apply(candidate):
    sample, request = candidate
    return restore.execute(
        sample.inputs, apply_local=True, upgrade_local=True, replay_preflight=request, environment=sample.environment
    )


def assert_retained(candidate):
    sample, _ = candidate
    assert sample.present() == (True, 2)
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone() == (8,)


def test_full_actual_candidate_preflight_is_readonly_and_does_not_replay(candidate, monkeypatch):
    snapshots = []
    observe(monkeypatch, snapshots)
    result = apply(candidate)
    proof = result["replay_preflight"]
    assert result["database_connections"] == 8 and proof["database_connections"] == 1
    assert proof["read_only"] is proof["local_preflight_completed"] is proof["central_tables_empty"] is True
    assert proof["mutations"] == proof["active_runs"] == proof["live_leases"] == 0
    assert proof["active_core_pins"] > 60 and proof["active_dependency_edges"] > 100
    assert proof["candidate_modules_checked"] > 20 and proof["owners_checked"] == 1
    assert (
        proof["latest_withdrawals_replayed"] is proof["runtime_verified"] is proof["native_restore_completed"] is False
    )
    assert proof["linux_attestation"] is proof["publication"] is False
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1], "READONLY_PREFLIGHT_CHANGED_COMPLETE_STATE"
    sample, _ = candidate
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute(
            "SELECT status,data FROM mingjing_core.core_entities WHERE id='synthetic-message'"
        ).fetchone() == ("active", {"text": "SYNTHETIC_PRIVATE_RESTORE_BODY"})


@pytest.mark.parametrize("module", ["tools", "mingjing_core"])
def test_actual_preloaded_control_namespace_is_refused_and_target_retained(candidate, monkeypatch, module):
    prefix = "import sys\nsys.path.insert(0," + repr(str(ROOT)) + ")\n__import__(" + repr(module) + ")\n"
    monkeypatch.setattr(process, "BOOTSTRAP", prefix + process.BOOTSTRAP)
    snapshots = []
    observe(monkeypatch, snapshots)
    with pytest.raises(RestoreRejected, match="PREFLIGHT_PRELOADED_BUSINESS"):
        apply(candidate)
    assert_retained(candidate)
    assert snapshots[0] == snapshots[1], "IMPORT_REFUSAL_CHANGED_TARGET"


def test_candidate_business_drift_after_upgrade_is_refused_with_target_preserved(candidate, monkeypatch):
    original = upgrade._upgrade_new_target

    def changed(inputs, dsns, creator):
        result = original(inputs, dsns, creator)
        path = inputs.contract.candidate_source / "mingjing_core/repositories/postgres.py"
        path.write_bytes(path.read_bytes() + b"\n# altered after upgrade\n")
        return result

    monkeypatch.setattr(upgrade, "_upgrade_new_target", changed)
    with pytest.raises(RestoreRejected, match="SOURCE_MEMBER_CHANGED"):
        apply(candidate)
    assert_retained(candidate)


def test_preflight_requires_same_call_apply_upgrade_without_any_connection(candidate, monkeypatch):
    sample, request = candidate

    def forbidden(*args, **kwargs):
        pytest.fail("PREFLIGHT_WITHOUT_APPLY_UPGRADE_MUST_NOT_CONNECT_OR_SPAWN")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(RestoreRejected, match="PREFLIGHT_REQUIRES_SAME_CALL_APPLY_UPGRADE"):
        restore.execute(sample.inputs, replay_preflight=request, environment=sample.environment)


@pytest.mark.parametrize("kind", ["owner", "active", "lease", "central"])
def test_real_target_refusal_is_readonly_and_never_repairs_or_clears_the_target(candidate, monkeypatch, kind):
    original = upgrade._upgrade_new_target

    def changed(inputs, dsns, creator):
        result = original(inputs, dsns, creator)
        with psycopg.connect(dsns["owner"]) as owner:
            if kind == "owner":
                owner.execute("INSERT INTO mingjing_core.core_owners(id) VALUES('synthetic-additional-owner')")
            elif kind == "central":
                owner.execute(
                    "INSERT INTO mingjing_core.core_model_accounts(account_id,ledger_identity,location_id) "
                    "VALUES('synthetic-account','00000000-0000-0000-0000-000000000001',%s)",
                    ("a" * 64,),
                )
            else:
                owner.execute(
                    "INSERT INTO mingjing_core.core_runs(id,owner,subject,operation_id,fingerprint,request,"
                    "call_limit,status,lease_until) VALUES('synthetic-run','synthetic','self','synthetic-run',"
                    "'synthetic','{}',2,%s,CASE WHEN %s THEN now()+interval '1 hour' ELSE NULL END)",
                    ("queued" if kind == "active" else "failed", kind == "lease"),
                )
        return result

    monkeypatch.setattr(upgrade, "_upgrade_new_target", changed)
    snapshots = []
    observe(monkeypatch, snapshots)
    code = {"owner": "PREFLIGHT_OWNER_SET", "central": "PREFLIGHT_CENTRAL_NOT_EMPTY"}.get(kind, "PREFLIGHT_ACTIVE_RUN")
    with pytest.raises(RestoreRejected, match=code):
        apply(candidate)
    assert_retained(candidate)
    assert snapshots[0] == snapshots[1], "REFUSED_PREFLIGHT_CHANGED_TARGET"
