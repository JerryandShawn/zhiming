"""Close cooperative service admission without claiming that existing writers have drained."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_incremental import BackupInputs
from tools.first_release_incremental_pg import admin_identity, identity, readonly, write_private
from tools.first_release_writer_fence import file_lock, pg_lock

Material = tuple[int, int, int, int, str]


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _stamp(path: Path, handle: Any = None) -> Material:
    ordinary(path)
    before = path.stat()
    require(before.st_size <= 16_000_000, "INCREMENTAL_ADMISSION_FILE_SIZE")
    expected = _identity(before)
    if handle is None:
        content = path.read_bytes()
    else:
        require(_identity(os.fstat(handle.fileno())) == expected, "INCREMENTAL_ADMISSION_FENCE_CHANGED")
        position = handle.tell()
        try:
            handle.seek(0)
            content = handle.read(before.st_size + 1)
        finally:
            handle.seek(position)
        require(_identity(os.fstat(handle.fileno())) == expected, "INCREMENTAL_ADMISSION_FENCE_CHANGED")
    ordinary(path)
    require(
        _identity(path.stat()) == expected and len(content) == before.st_size,
        "INCREMENTAL_ADMISSION_FILE_CHANGED",
    )
    return *expected, hashlib.sha256(content).hexdigest()


def marker_material(inputs: BackupInputs) -> Material:
    """A matching marker is retained material, never permission to skip the M1 gates."""
    before = _stamp(inputs.maintenance)
    require(before[2] <= 4096, "INCREMENTAL_ADMISSION_MARKER_SIZE")
    try:
        value = json.loads(inputs.maintenance.read_bytes())
    except (OSError, ValueError, UnicodeError):
        raise RestoreRejected("INCREMENTAL_ADMISSION_MARKER_UNREADABLE") from None
    require(
        type(value) is dict
        and set(value) == {"operation_id", "database_oid"}
        and type(value["operation_id"]) is str
        and type(value["database_oid"]) is int
        and value == {"operation_id": inputs.operation_id, "database_oid": inputs.source.database_oid},
        "INCREMENTAL_ADMISSION_MARKER_BINDING",
    )
    require(_stamp(inputs.maintenance) == before, "INCREMENTAL_ADMISSION_MARKER_CHANGED")
    return before


def unchanged_marker(inputs: BackupInputs, expected: Material) -> None:
    require(marker_material(inputs) == expected, "INCREMENTAL_ADMISSION_MARKER_CHANGED")


def close_admission(inputs: BackupInputs, dsns: dict[str, str]) -> dict[str, Any]:
    receipt = inputs.validate()
    with (
        file_lock(inputs.fence_path, exclusive=False, existing_only=True, return_handle=True) as fence,
        psycopg.connect(readonly(dsns["admin"]), autocommit=True, row_factory=dict_row) as admin,
        psycopg.connect(readonly(dsns["owner"]), autocommit=True, row_factory=dict_row) as owner,
    ):
        initial = _stamp(inputs.fence_path, fence)
        identity(owner, inputs, "owner")
        with pg_lock(owner, inputs.fence_key, exclusive=False):
            fields = conninfo_to_dict(dsns["admin"])
            admin_identity(admin, inputs, fields)
            with psycopg.connect(readonly(dsns["writer"]), row_factory=dict_row) as writer:
                identity(writer, inputs, "writer")
            identity(owner, inputs, "owner")
            require(_stamp(inputs.fence_path, fence) == initial, "INCREMENTAL_ADMISSION_FENCE_CHANGED")
            require(not os.path.lexists(inputs.maintenance), "INCREMENTAL_MAINTENANCE_ALREADY_PRESENT")
            write_private(
                inputs.maintenance,
                {"operation_id": inputs.operation_id, "database_oid": inputs.source.database_oid},
            )
            retained = marker_material(inputs)
            admin_identity(admin, inputs, fields)
            identity(owner, inputs, "owner")
            require(_stamp(inputs.fence_path, fence) == initial, "INCREMENTAL_ADMISSION_FENCE_CHANGED")
            inputs.validate()
            unchanged_marker(inputs, retained)
    return dict(
        receipt,
        schema="first-release-local-admission-v1",
        operation_id=inputs.operation_id,
        source_database_oid=inputs.source.database_oid,
        admission_closed=True,
        maintenance_retained=True,
        marker_sha256=retained[-1],
        database_connections=3,
        file_writes=1,
        business_mutations=0,
        drained=False,
        global_quiescence_verified=False,
    )
