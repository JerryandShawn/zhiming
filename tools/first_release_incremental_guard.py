"""Read-only existing-source observations under the retained M1 cooperative fences; no DDL authority."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from tools.first_release_capture_binding import CaptureBinding
from tools.first_release_contracts import RestoreRejected, digest, ordinary, require
from tools.first_release_incremental import HERE, BackupInputs, connections, file_hash
from tools.first_release_incremental_pg import (
    admin_identity,
    identity,
    readonly,
    sessions,
    snapshot,
    source_scope,
)
from tools.first_release_local_inputs import LocalInputs
from tools.first_release_source_profile import verify_source_profile
from tools.first_release_writer_fence import file_lock, pg_lock

CONTROLS = frozenset(
    {
        "first_release_incremental_guard.py",
        "first_release_source_profile.py",
        "first_release_acl.py",
    }
)


def check_controls(controls: tuple[tuple[str, str], ...]) -> None:
    require(
        type(controls) is tuple
        and all(type(row) is tuple and len(row) == 2 for row in controls)
        and len(controls) == len(CONTROLS)
        and set(dict(controls)) == CONTROLS,
        "SOURCE_GUARD_CONTROL_SET",
    )
    for name, expected in controls:
        ordinary(HERE / name)
        require(
            digest(expected) and file_hash(HERE / name) == expected,
            "SOURCE_GUARD_CONTROL_CHANGED",
        )


def capture_baseline(source: BackupInputs, target: LocalInputs, binding: CaptureBinding) -> dict[str, Any]:
    require(
        type(source) is BackupInputs and type(target) is LocalInputs and type(binding) is CaptureBinding,
        "SOURCE_GUARD_TYPED_INPUTS",
    )
    target.validate()
    original, state = binding.validate(target)
    require(original == source, "SOURCE_GUARD_ORIGINAL_CAPTURE_BINDING")
    return state


def stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def file_stamp(path: Path, handle: Any = None) -> tuple[int, int, int, int, str]:
    ordinary(path)
    before = path.stat()
    require(before.st_size <= 16_000_000, "SOURCE_GUARD_FILE_SIZE")
    first = stat_identity(before)
    if handle is None:
        content = path.read_bytes()
    else:
        require(
            stat_identity(os.fstat(handle.fileno())) == first,
            "SOURCE_GUARD_FENCE_HANDLE_CHANGED",
        )
        position = handle.tell()
        try:
            handle.seek(0)
            content = handle.read(before.st_size + 1)
        finally:
            handle.seek(position)
        require(
            stat_identity(os.fstat(handle.fileno())) == first,
            "SOURCE_GUARD_FENCE_HANDLE_CHANGED",
        )
    ordinary(path)
    require(
        stat_identity(path.stat()) == first and len(content) == before.st_size,
        "SOURCE_GUARD_FILE_RACED",
    )
    return *first, hashlib.sha256(content).hexdigest()


def maintenance_material(source: BackupInputs, fence_handle: Any = None) -> dict[str, tuple[int, int, int, int, str]]:
    expected = {
        "operation_id": source.operation_id,
        "database_oid": source.source.database_oid,
    }
    materials = {}
    for path in (
        source.fence_path,
        source.maintenance,
        source.operation_dir / "backup-started.json",
    ):
        before = file_stamp(path, fence_handle if path == source.fence_path else None)
        if path != source.fence_path:
            value = json.loads(path.read_bytes())
            require(
                type(value) is dict
                and set(value) == set(expected)
                and type(value["operation_id"]) is str
                and type(value["database_oid"]) is int
                and value == expected,
                "SOURCE_GUARD_MAINTENANCE_BINDING",
            )
            require(file_stamp(path) == before, "SOURCE_GUARD_FILE_RACED")
        materials[str(path)] = before
    return materials


def checked_writer(owner: Any, dsns: dict[str, str], source: BackupInputs) -> None:
    with (
        psycopg.connect(readonly(dsns["writer"]), autocommit=True, row_factory=dict_row) as writer,
        writer.transaction(),
    ):
        writer.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        pid = identity(writer, source, "writer")
        sessions(owner, {owner.info.backend_pid, pid})
        verify_source_profile(writer, source, "writer")
        sessions(owner, {owner.info.backend_pid, pid})
    sessions(owner, {owner.info.backend_pid})


def checked_owner(owner: Any, source: BackupInputs, baseline: dict[str, Any]) -> None:
    sessions(owner, {owner.info.backend_pid})
    with owner.transaction():
        owner.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        identity(owner, source, "owner")
        verify_source_profile(owner, source, "owner")
        source_scope(owner, source)
        require(snapshot(owner) == baseline, "SOURCE_GUARD_CAPTURE_STATE_CHANGED")
    sessions(owner, {owner.info.backend_pid})


def checked_materials(
    source: BackupInputs,
    target: LocalInputs,
    binding: CaptureBinding,
    controls: tuple[tuple[str, str], ...],
    baseline: dict[str, Any],
    materials: dict[str, tuple[int, int, int, int, str]],
    fence_handle: Any,
) -> None:
    check_controls(controls)
    require(
        capture_baseline(source, target, binding) == baseline,
        "SOURCE_GUARD_CAPTURE_CHANGED",
    )
    require(
        maintenance_material(source, fence_handle) == materials,
        "SOURCE_GUARD_MAINTENANCE_CHANGED",
    )


@contextmanager
def held_source(
    source: BackupInputs,
    target: LocalInputs,
    binding: CaptureBinding,
    *,
    controls: tuple[tuple[str, str], ...],
    environment: Mapping[str, str] | None = None,
) -> Iterator[None]:
    """Yield no connection or capability; success observes unchanged data, never permits source writes."""
    try:
        check_controls(controls)
        baseline = capture_baseline(source, target, binding)
        materials = maintenance_material(source)
        dsns = connections(source, None if environment is None else dict(environment))
        with file_lock(source.fence_path, exclusive=True, existing_only=True, return_handle=True) as fence_handle:
            require(
                maintenance_material(source, fence_handle) == materials,
                "SOURCE_GUARD_MAINTENANCE_CHANGED",
            )
            with psycopg.connect(readonly(dsns["admin"]), row_factory=dict_row) as admin:
                admin_identity(admin, source, conninfo_to_dict(dsns["admin"]))
            with psycopg.connect(readonly(dsns["owner"]), autocommit=True, row_factory=dict_row) as owner:
                identity(owner, source, "owner")
                with pg_lock(owner, source.fence_key, exclusive=True):
                    checked_writer(owner, dsns, source)
                    checked_owner(owner, source, baseline)
                    checked_materials(
                        source,
                        target,
                        binding,
                        controls,
                        baseline,
                        materials,
                        fence_handle,
                    )
                    yield None
                    checked_materials(
                        source,
                        target,
                        binding,
                        controls,
                        baseline,
                        materials,
                        fence_handle,
                    )
                    checked_writer(owner, dsns, source)
                    checked_owner(owner, source, baseline)
                    checked_materials(
                        source,
                        target,
                        binding,
                        controls,
                        baseline,
                        materials,
                        fence_handle,
                    )
    except psycopg.Error:
        raise RestoreRejected("SOURCE_GUARD_QUERY_FAILED") from None
    except (OSError, ValueError, UnicodeError):
        raise RestoreRejected("SOURCE_GUARD_MATERIAL_FAILED") from None
