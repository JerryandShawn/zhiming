"""Read-only source guard against real M1 captures; fixture mutations are synthetic test-owned faults."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from test_first_release_capture_binding_pg import captured as shared_captured
from test_first_release_capture_binding_pg import source_document
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import existing as shared_existing
from test_first_release_incremental_backup_pg import state
from test_first_release_source_profile_pg import legal as shared_legal

from mingjing_core.repositories.postgres import PostgresRepository
from tools import first_release_incremental_guard as guard
from tools import first_release_writer_fence as fence
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import HERE, BackupInputs, file_hash


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    yield from shared_existing.__wrapped__(request, archive)


@pytest.fixture
def captured(existing):
    # Establish the legitimate original writer ACL before the capture; the guard never repairs it.
    source = shared_legal.__wrapped__(existing)
    source.inputs = BackupInputs.parse(source_document(source.inputs), source.inputs.workspace)
    with contextmanager(shared_captured.__wrapped__)(source, SimpleNamespace()) as case:
        yield case


def controls():
    return tuple(sorted((name, file_hash(HERE / name)) for name in guard.CONTROLS))


def held(case, *, reviewed=None):
    return guard.held_source(
        case.source.inputs,
        case.inputs,
        case.binding,
        controls=controls() if reviewed is None else reviewed,
        environment=case.source.environment,
    )


def files(case):
    source = case.source.inputs
    return {
        str(path): (path.stat().st_dev, path.stat().st_ino, path.read_bytes())
        for path in (
            source.fence_path,
            source.maintenance,
            source.operation_dir / "backup-started.json",
        )
    }


def test_existing_only_missing_or_removed_fence_never_creates_a_replacement(tmp_path, monkeypatch):
    missing = tmp_path / "missing.lock"
    with (
        pytest.raises(RestoreRejected, match="^INCREMENTAL_EXISTING_FENCE_REQUIRED$"),
        fence.file_lock(missing, exclusive=True, existing_only=True),
    ):
        pytest.fail("missing fence entered its scope")
    assert not missing.exists()
    raced = tmp_path / "raced.lock"
    with fence.file_lock(raced, exclusive=True) as value:
        assert value is None and raced.exists()
    raced.write_bytes(b"synthetic")
    original = raced.stat()
    with fence.file_lock(raced, exclusive=True, existing_only=True, return_handle=True) as locked:
        assert locked.read() == b"synthetic"
        if os.name == "nt":
            with pytest.raises(PermissionError):
                raced.read_bytes()
    actual = raced.stat()
    assert (original.st_dev, original.st_ino) == (actual.st_dev, actual.st_ino)
    assert raced.read_bytes() == b"synthetic"
    opened = fence.os.open

    def removed(path, flags, *args, **kwargs):
        if Path(path) == raced:
            raced.unlink()
        return opened(path, flags, *args, **kwargs)

    monkeypatch.setattr(fence.os, "open", removed)
    with (
        pytest.raises(RestoreRejected, match="^INCREMENTAL_EXISTING_FENCE_REQUIRED$"),
        fence.file_lock(raced, exclusive=True, existing_only=True),
    ):
        pytest.fail("raced fence entered its scope")
    assert not raced.exists()


@pytest.mark.parametrize("existing", [4, 7], indirect=True)
def test_real_capture_source_guard_is_readonly_and_holds_original_both_fences(captured, monkeypatch):
    before, material = state(captured.source), files(captured)
    connect = psycopg.connect
    observed = []

    def recording(dsn, *args, **kwargs):
        connection = connect(dsn, *args, **kwargs)
        observed.append(
            (
                connection.info.backend_pid,
                "default_transaction_read_only=on" in conninfo_to_dict(dsn)["options"],
            )
        )
        return connection

    monkeypatch.setattr(guard.psycopg, "connect", recording)
    with held(captured) as value:
        assert value is None
        with (
            pytest.raises(RestoreRejected, match="^INCREMENTAL_FILE_FENCE_BUSY$"),
            fence.file_lock(captured.source.inputs.fence_path, exclusive=True, existing_only=True),
        ):
            pytest.fail("source file fence was not held")
        with connect(
            captured.source.environment["FIRST_INCREMENTAL_OWNER_DSN"],
            row_factory=dict_row,
        ) as other:
            result = other.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok",
                (captured.source.inputs.fence_key,),
            ).fetchone()
            assert result == {"ok": False}
    assert len(observed) == 4 and all(pid > 0 for pid, _ in observed)
    assert all(readonly for _, readonly in observed)
    monkeypatch.undo()
    assert state(captured.source) == before and files(captured) == material


def test_guard_control_drift_rejects_before_any_connection(captured, monkeypatch):
    reviewed = list(controls())
    reviewed[0] = reviewed[0][0], "0" * 64
    before = state(captured.source)

    def forbidden(*args, **kwargs):
        pytest.fail("bad controls reached PostgreSQL")

    with monkeypatch.context() as patch:
        patch.setattr(guard.psycopg, "connect", forbidden)
        with (
            pytest.raises(RestoreRejected, match="^SOURCE_GUARD_CONTROL_CHANGED$"),
            held(captured, reviewed=tuple(reviewed)),
        ):
            pytest.fail("bad controls entered source scope")
    assert state(captured.source) == before


@pytest.mark.parametrize("fault", ["missing-fence", "missing-marker", "invalid-started"])
def test_missing_or_malformed_retained_material_is_rejected_without_repair(captured, fault, monkeypatch):
    source = captured.source.inputs
    if fault == "missing-fence":
        source.fence_path.unlink()
    elif fault == "missing-marker":
        source.maintenance.unlink()
    else:
        path = source.operation_dir / "backup-started.json"
        value = json.loads(path.read_bytes())
        path.write_text(json.dumps(dict(value, extra=True)), encoding="utf-8")
    before = state(captured.source)
    paths = (
        source.fence_path,
        source.maintenance,
        source.operation_dir / "backup-started.json",
    )
    material = {str(path): path.read_bytes() if path.exists() else None for path in paths}

    def forbidden(*args, **kwargs):
        pytest.fail("invalid retained material reached PostgreSQL")

    with monkeypatch.context() as patch:
        patch.setattr(guard.psycopg, "connect", forbidden)
        with (
            pytest.raises(
                RestoreRejected,
                match="^SOURCE_GUARD_(MATERIAL_FAILED|MAINTENANCE_BINDING)$",
            ),
            held(captured),
        ):
            pytest.fail("invalid retained material entered source scope")
    assert state(captured.source) == before
    assert {str(path): path.read_bytes() if path.exists() else None for path in paths} == material


def test_same_bytes_replaced_marker_is_detected_when_leaving_scope(captured):
    source = captured.source.inputs
    before = state(captured.source)
    old = source.maintenance.stat()
    with (
        pytest.raises(RestoreRejected, match="^SOURCE_GUARD_MAINTENANCE_CHANGED$"),
        held(captured),
    ):
        replacement = source.maintenance.with_suffix(".synthetic-replacement")
        replacement.write_bytes(source.maintenance.read_bytes())
        replacement.replace(source.maintenance)
        actual = source.maintenance.stat()
        assert (actual.st_dev, actual.st_ino) != (old.st_dev, old.st_ino)
    assert state(captured.source) == before and source.maintenance.is_file()


def test_actual_timestamp_field_drift_stops_without_reverting_source(captured):
    with psycopg.connect(captured.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        owner.execute("UPDATE mingjing_core.core_entities SET updated_at=updated_at+interval '1 second'")
    changed = state(captured.source)
    with (
        pytest.raises(RestoreRejected, match="^SOURCE_GUARD_CAPTURE_STATE_CHANGED$"),
        held(captured),
    ):
        pytest.fail("changed capture point entered scope")
    assert state(captured.source) == changed


@pytest.mark.parametrize("fault", ["busy", "other-session"])
def test_actual_queued_run_or_unowned_live_pid_is_never_exempted(captured, fault):
    dsn = captured.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    if fault == "busy":
        repository = PostgresRepository(dsn, initialize=False, max_size=1)
        try:
            repository.queue_run("synthetic", "synthetic-guard-queue", {"synthetic": True}, depth="fast")
        finally:
            repository.close()
        before = state(captured.source)
        with (
            pytest.raises(RestoreRejected, match="^INCREMENTAL_ACTIVE_RUN_OR_LEASE$"),
            held(captured),
        ):
            pytest.fail("busy source entered scope")
    else:
        before = state(captured.source)
        with psycopg.connect(dsn) as other:
            assert other.info.backend_pid > 0
            with (
                pytest.raises(RestoreRejected, match="^INCREMENTAL_OTHER_SOURCE_SESSION$"),
                held(captured),
            ):
                pytest.fail("unowned PID entered source scope")
    assert state(captured.source) == before


def test_unreviewed_relation_is_refused_by_actual_source_profile(captured):
    with psycopg.connect(captured.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        owner.execute("CREATE VIEW public.synthetic_guard_view AS SELECT 1 AS synthetic")
    before = state(captured.source)
    with (
        pytest.raises(RestoreRejected, match="^SOURCE_PROFILE_RELATIONS_OR_SEQUENCE$"),
        held(captured),
    ):
        pytest.fail("extra relation entered scope")
    assert state(captured.source) == before
