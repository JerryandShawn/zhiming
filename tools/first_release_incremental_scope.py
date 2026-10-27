"""Private same-call source fences and opaque forward authority; never a JSON permission."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from tools import first_release_incremental_guard as guard
from tools.first_release_contracts import require
from tools.first_release_controller_runtime import RuntimeWitness, verified_saver
from tools.first_release_incremental import connections
from tools.first_release_incremental_pg import admin_identity, identity, readonly, sessions, snapshot, source_scope
from tools.first_release_source_profile import checked_identity, verify_source_profile, writer_privileges
from tools.first_release_target_proof import TargetProof, consume_target_proof
from tools.first_release_writer_fence import file_lock, pg_lock

_SEAL = object()


class SourceUpgradeWitness:
    __slots__ = ()

    def __new__(cls, seal: object = None) -> SourceUpgradeWitness:
        require(cls is SourceUpgradeWitness and seal is _SEAL, "SOURCE_FORWARD_OPAQUE_WITNESS_REQUIRED")
        return super().__new__(cls)

    def __reduce__(self) -> Any:
        from tools.first_release_contracts import RestoreRejected

        raise RestoreRejected("SOURCE_FORWARD_WITNESS_NOT_SERIALIZABLE")


@dataclass
class _Scope:
    request: Any
    baseline: dict[str, Any]
    materials: dict[str, Any]
    dsns: dict[str, str] = field(repr=False)
    owner: Any = field(repr=False)
    fence: Any = field(repr=False)
    pid: int
    checkpoint_versions: tuple[int, ...] = ()
    phase: str = "source_checks"
    session_restored: bool = True


@dataclass(frozen=True)
class _Authority:
    scope: _Scope
    runtime: RuntimeWitness
    target_summary: dict[str, Any]


_SCOPES: dict[int, _Scope] = {}
_WITNESSES: dict[SourceUpgradeWitness, _Authority] = {}


def _prefer_failure(first: BaseException | None, incoming: BaseException) -> BaseException:
    controls = (KeyboardInterrupt, SystemExit, GeneratorExit)
    if isinstance(first, controls):
        return first
    if isinstance(incoming, controls):
        return incoming
    return incoming if first is None else first


def _materials(scope: _Scope) -> None:
    scope.request.validate()
    guard.checked_materials(
        scope.request.source,
        scope.request.target,
        scope.request.capture,
        scope.request.guard_controls(),
        scope.baseline,
        scope.materials,
        scope.fence,
    )


def _versions(connection: Any) -> tuple[int, ...]:
    values = tuple(row["v"] for row in connection.execute("SELECT v FROM public.checkpoint_migrations ORDER BY v"))
    require(
        all(type(value) is int for value in values) and values == tuple(range(len(values))),
        "SOURCE_FORWARD_ORIGINAL_CHECKPOINT_HISTORY",
    )
    return values


def _initial_state(scope: _Scope) -> None:
    source, owner = scope.request.source, scope.owner
    sessions(owner, {scope.pid})
    with owner.transaction():
        owner.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        identity(owner, source, "owner")
        verify_source_profile(owner, source, "owner")
        source_scope(owner, source)
        require(snapshot(owner) == scope.baseline, "SOURCE_FORWARD_CAPTURE_STATE_CHANGED")
        versions = _versions(owner)
    if scope.checkpoint_versions:
        require(versions == scope.checkpoint_versions, "SOURCE_FORWARD_CHECKPOINT_HISTORY_CHANGED")
    scope.checkpoint_versions = versions
    sessions(owner, {scope.pid})


def _registered(scope: _Scope) -> None:
    require(
        _SCOPES.get(id(scope)) is scope
        and isinstance(scope.owner, psycopg.Connection)
        and not scope.owner.closed
        and scope.owner.info.backend_pid == scope.pid
        and not scope.fence.closed,
        "SOURCE_FORWARD_SCOPE_EXPIRED",
    )
    identity(scope.owner, scope.request.source, "owner")
    locked = scope.owner.execute(
        "WITH key AS (SELECT hashtextextended(%s,0) AS value) "
        "SELECT EXISTS(SELECT 1 FROM pg_locks,key WHERE locktype='advisory' "
        "AND database=%s AND pid=%s AND pid=pg_backend_pid() AND mode='ExclusiveLock' AND granted "
        "AND classid::bigint=((key.value>>32)&4294967295) "
        "AND objid::bigint=(key.value&4294967295) AND objsubid=1) AS locked",
        (scope.request.source.fence_key, scope.request.source.source.database_oid, scope.pid),
    ).fetchone()
    require(locked and locked["locked"], "SOURCE_FORWARD_LIVE_PG_FENCE_REQUIRED")
    _materials(scope)


def _active(witness: SourceUpgradeWitness, expected: str) -> _Authority:
    require(type(witness) is SourceUpgradeWitness, "SOURCE_FORWARD_OPAQUE_WITNESS_REQUIRED")
    authority = _WITNESSES.get(witness)
    require(authority is not None, "SOURCE_FORWARD_WITNESS_EXPIRED")
    _registered(authority.scope)
    require(authority.scope.phase == expected, "SOURCE_FORWARD_PHASE_ORDER")
    return authority


@contextmanager
def _held_forward(request: Any, baseline: dict[str, Any]) -> Iterator[_Scope]:
    from tools.first_release_incremental_forward import ForwardInputs

    require(type(request) is ForwardInputs, "SOURCE_FORWARD_TYPED_REQUEST")
    request.validate()
    source = request.source
    materials = guard.maintenance_material(source)
    dsns = connections(source, None if request.environment is None else dict(request.environment))
    with file_lock(source.fence_path, exclusive=True, existing_only=True, return_handle=True) as fence:
        require(guard.maintenance_material(source, fence) == materials, "SOURCE_FORWARD_MAINTENANCE_CHANGED")
        with psycopg.connect(readonly(dsns["admin"]), row_factory=dict_row) as admin:
            admin_identity(admin, source, conninfo_to_dict(dsns["admin"]))
        with psycopg.connect(readonly(dsns["owner"]), autocommit=True, row_factory=dict_row) as owner:
            pid = identity(owner, source, "owner")
            with pg_lock(owner, source.fence_key, exclusive=True):
                scope = _Scope(request, baseline, materials, dsns, owner, fence, pid)
                _SCOPES[id(scope)] = scope
                try:
                    guard.checked_writer(owner, dsns, source)
                    _initial_state(scope)
                    _materials(scope)
                    yield scope
                finally:
                    _SCOPES.pop(id(scope), None)
                    for witness, authority in tuple(_WITNESSES.items()):
                        if authority.scope is scope:
                            _WITNESSES.pop(witness, None)


@contextmanager
def _authorized(scope: _Scope, proof: TargetProof, runtime: RuntimeWitness) -> Iterator[SourceUpgradeWitness]:
    _registered(scope)
    saver = verified_saver(runtime)
    require(len(scope.checkpoint_versions) <= len(saver.MIGRATIONS), "SOURCE_FORWARD_NEWER_CHECKPOINT_HISTORY")
    target = consume_target_proof(proof, source=scope.request.source)
    guard.checked_writer(scope.owner, scope.dsns, scope.request.source)
    _initial_state(scope)
    _materials(scope)
    witness = SourceUpgradeWitness(_SEAL)
    scope.phase = "authorized"
    _WITNESSES[witness] = _Authority(scope, runtime, target)
    try:
        yield witness
    finally:
        _WITNESSES.pop(witness, None)


def prepare_locked_source(witness: SourceUpgradeWitness, connection: Any) -> None:
    authority = _active(witness, "core_transaction_started")
    scope, source = authority.scope, authority.scope.request.source
    require(connection is scope.owner, "SOURCE_FORWARD_SAME_OWNER_REQUIRED")
    settings = connection.execute(
        "SELECT current_setting('transaction_isolation') AS isolation,current_setting('transaction_read_only') AS ro"
    ).fetchone()
    require(settings == {"isolation": "read committed", "ro": "off"}, "SOURCE_FORWARD_FRESH_RW_TRANSACTION_REQUIRED")
    for name in sorted(scope.baseline["tables"]):
        connection.execute(
            sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE NOWAIT").format(sql.Identifier(*name.split(".")))
        )
    identity(connection, source, "owner")
    verify_source_profile(connection, source, "owner")
    source_scope(connection, source)
    sessions(connection, {scope.pid})
    require(snapshot(connection) == scope.baseline, "SOURCE_FORWARD_LOCKED_CAPTURE_CHANGED")
    require(_versions(connection) == scope.checkpoint_versions, "SOURCE_FORWARD_CHECKPOINT_HISTORY_CHANGED")
    require(
        len(scope.checkpoint_versions) <= len(verified_saver(authority.runtime).MIGRATIONS),
        "SOURCE_FORWARD_NEWER_CHECKPOINT_HISTORY",
    )
    _materials(scope)


def pregrant_original_acl(witness: SourceUpgradeWitness) -> None:
    scope = _active(witness, "checkpoint_completed").scope
    source = scope.request.source
    with (
        psycopg.connect(readonly(scope.dsns["writer"]), autocommit=True, row_factory=dict_row) as writer,
        writer.transaction(),
    ):
        writer.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        checked_identity(writer, source, "writer")
        sessions(scope.owner, {scope.pid, writer.info.backend_pid})
        rows = writer.execute(
            "SELECT c.oid,n.nspname||'.'||c.relname AS name FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname||'.'||c.relname=ANY(%s) AND c.relkind='r' AND c.relowner=%s",
            (list(scope.baseline["tables"]), source.source.owner_oid),
        ).fetchall()
        require({row["name"] for row in rows} == set(scope.baseline["tables"]), "SOURCE_FORWARD_ORIGINAL_ACL_RELATIONS")
        writer_privileges(writer, source, rows)
        sessions(scope.owner, {scope.pid, writer.info.backend_pid})
    sessions(scope.owner, {scope.pid})


def checkpoint(witness: SourceUpgradeWitness) -> int:
    authority = _active(witness, "core_verified")
    scope = authority.scope
    saver = verified_saver(authority.runtime)
    _materials(scope)
    scope.phase, scope.session_restored = "checkpoint_started", False
    failure: BaseException | None = None
    try:
        scope.owner.execute("SET default_transaction_read_only=off")
        scope.owner.execute("SET search_path=public")
        saver(scope.owner).setup()
        require(verified_saver(authority.runtime) is saver, "SOURCE_FORWARD_SAVER_CHANGED_AFTER_SETUP")
        count = len(saver.MIGRATIONS)
        scope.phase = "checkpoint_completed"
    except BaseException as error:
        failure = _prefer_failure(failure, error)
    try:
        scope.owner.execute("SET default_transaction_read_only=on")
        scope.owner.execute("SET search_path=pg_catalog")
        scope.session_restored = True
    except BaseException as error:
        failure = _prefer_failure(failure, error)
    if failure is not None:
        raise failure
    return count
