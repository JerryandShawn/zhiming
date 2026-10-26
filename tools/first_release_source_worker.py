"""Fresh local fr_upgrade worker; no source authority is reconstructed from its JSON payload."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import runpy
import sys
from pathlib import Path
from typing import Any

PHASES = (
    "first_apply_started",
    "first_native_completed",
    "first_verified",
    "second_apply_started",
    "second_native_completed",
    "second_verified",
)
CONTROL_LOADS = frozenset(
    {
        "first_release_replay_worker.py",
        "first_release_replay_effects.py",
        "first_release_source_effects.py",
        "first_release_source_pool.py",
        "first_release_incremental_pg.py",
    }
)


class Blocked(BaseException):
    """Control stops must escape ordinary exception handlers in native candidate code."""


def require(value: Any, code: str) -> None:
    if not value:
        raise Blocked(code)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ordinary(path: Path) -> None:
    require(
        path.is_absolute() and path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        "SOURCE_REPLAY_CONTROL_ORIGIN",
    )


def checked_controls(value: Any) -> None:
    root = Path(value["control_root"])
    require(
        type(value["controls"]) is dict and value["controls"] == dict(value["pin"]["controls"]),
        "SOURCE_REPLAY_CONTROL_BINDING",
    )
    require({Path(name).name for name in value["controls"]} >= CONTROL_LOADS, "SOURCE_REPLAY_CONTROL_BINDING")
    for name, sha in value["controls"].items():
        require(
            re.fullmatch(r"(?:tools|mingjing_core/repositories)/[a-z][a-z0-9_]*\.py", name)
            and type(sha) is str
            and re.fullmatch(r"[0-9a-f]{64}", sha),
            "SOURCE_REPLAY_CONTROL_BINDING",
        )
        path = root / name
        _ordinary(path)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == sha, "SOURCE_REPLAY_CONTROL_CHANGED")


def load_control(value: Any, name: str) -> Any:
    require(name in CONTROL_LOADS, "SOURCE_REPLAY_CONTROL_BINDING")
    checked_controls(value)
    return runpy.run_path(str(Path(value["control_root"]) / "tools" / name), run_name="__reviewed_" + name[:-3])


def _admit(value: Any) -> None:
    fields = {
        "schema",
        "local_drill",
        "worker",
        "control_root",
        "controls",
        "root",
        "python",
        "pin",
        "source",
        "operation_id",
        "parent_pid",
        "nonce",
        "core_lock_sha256",
        "migrations",
        "replay",
    }
    require(
        type(value) is dict
        and set(value) == fields
        and value["local_drill"] is True
        and value["schema"] == "first-release-local-source-worker-v1",
        "SOURCE_REPLAY_LOCAL_INPUT",
    )
    require(
        type(value["operation_id"]) is str
        and re.fullmatch(r"fr-[0-9a-f]{32}", value["operation_id"])
        and value["source"]["database"] == "fr_upgrade_" + value["operation_id"][3:]
        and type(value["parent_pid"]) is int
        and value["parent_pid"] > 0
        and re.fullmatch(r"[0-9a-f]{64}", value["nonce"]),
        "SOURCE_REPLAY_SOURCE_IDENTITY",
    )
    require(
        not any(name.split(".")[0] in {"tools", "mingjing_core"} for name in sys.modules),
        "SOURCE_REPLAY_PRELOADED_BUSINESS",
    )
    require(
        Path(value["worker"]) == Path(value["control_root"]) / "tools/first_release_source_worker.py",
        "SOURCE_REPLAY_WORKER_ORIGIN",
    )
    checked_controls(value)


def _candidate(value: Any, foundation: Any) -> tuple[Any, Any, Any, Any, Any]:
    root = Path(value["root"])
    path = root / "__release_manifest__.json"
    _ordinary(path)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == value["pin"]["manifest_sha256"], "SOURCE_REPLAY_SOURCE_CHANGED")
    manifest = json.loads(raw)
    require(manifest["commit"] == value["pin"]["candidate"], "SOURCE_REPLAY_SOURCE_CHANGED")
    files = manifest["files"]
    sys.meta_path.insert(0, foundation["CandidateFinder"](root, files))
    sys.path.insert(0, str(root))
    sites, _ = foundation["runtime"](value, root)
    repository = importlib.import_module("mingjing_core.repositories.postgres")
    deployment = importlib.import_module("tools.deploy_core")
    monotone = importlib.import_module("tools.b1_restore_proof_contracts").verify_monotone
    for function in (
        deployment.apply_withdrawals,
        deployment.export_withdrawals,
        monotone,
        repository.PostgresRepository.verify_schema,
    ):
        foundation["verified"](function.__code__.co_filename, root, files)

    def audit() -> None:
        checked_controls(value)
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == value["pin"]["manifest_sha256"],
            "SOURCE_REPLAY_SOURCE_CHANGED",
        )
        for name, sha in value["pin"]["locks"]:
            require(
                name in {"requirements-core.lock", "requirements-charts.lock", "k3-tokenizer.lock.json"},
                "SOURCE_REPLAY_LOCK_SET",
            )
            item = root / name
            _ordinary(item)
            require(hashlib.sha256(item.read_bytes()).hexdigest() == sha, "SOURCE_REPLAY_SOURCE_CHANGED")
        for name, entry in files.items():
            if name.startswith("mingjing_core/repositories/migrations/") and name.endswith(".sql"):
                item = root / name
                _ordinary(item)
                require(
                    hashlib.sha256(item.read_bytes()).hexdigest() == entry["sha256"], "SOURCE_REPLAY_SOURCE_CHANGED"
                )
        foundation["third_party_origins"](sites)
        foundation["business_origins"](root, files)

    audit()
    return repository, deployment, monotone, audit, foundation


def _repository(value: Any, repository: Any, pool: Any) -> tuple[Any, Any]:
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    require(not any(key.startswith("PG") and item for key, item in os.environ.items()), "SOURCE_REPLAY_IMPLICIT_PG")
    dsn = os.environ.get("FIRST_RELEASE_SOURCE_OWNER_DSN", "")
    fields = conninfo_to_dict(dsn)
    require(
        set(fields) <= {"host", "hostaddr", "port", "dbname", "user", "password", "passfile", "connect_timeout"}
        and fields.get("host") in {"127.0.0.1", "::1"}
        and fields.get("port") in {"55480", "55481"}
        and fields.get("hostaddr", fields["host"]) == fields["host"]
        and fields.get("passfile", os.devnull) == os.devnull
        and fields.get("dbname") == value["source"]["database"]
        and fields.get("user") == value["source"]["database"] + "_owner",
        "SOURCE_REPLAY_LOCAL_DSN",
    )
    source_class = importlib.import_module("tools.first_release_incremental").SourcePin
    source = source_class.parse(value["source"])
    expected = pool["ExpectedPoolIdentity"](
        value["operation_id"], source, fields["host"], int(fields["port"]), value["parent_pid"]
    )
    expected.validate()
    actual = make_conninfo(
        dsn,
        passfile=os.devnull,
        connect_timeout=5,
        options="-c default_transaction_read_only=on -c search_path=pg_catalog,public -c TimeZone=UTC",
    )
    return repository.PostgresRepository(actual, initialize=False, max_size=1), expected


def _source(repo: Any, value: Any) -> dict[str, Any]:
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        require(
            repo.verify_schema()["checksums"] == value["migrations"]
            and set(value["migrations"]) == {str(i) for i in range(1, 9)},
            "SOURCE_REPLAY_HISTORY_1_8",
        )
        owners = sorted(row["id"] for row in connection.execute("SELECT id FROM mingjing_core.core_owners"))
        require(owners == value["source"]["owners"], "SOURCE_REPLAY_OWNER_SET")
        require(
            not connection.execute(
                "SELECT EXISTS(SELECT 1 FROM mingjing_core.core_runs WHERE status IN ('queued','running') "
                "OR lease_until>clock_timestamp()) AS busy"
            ).fetchone()["busy"],
            "SOURCE_REPLAY_ACTIVE_OR_LEASED",
        )
        objects = connection.execute(
            "SELECT c.relowner FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind IN ('r','p','S','v','m','f')"
        ).fetchall()
        require(
            objects and all(row["relowner"] == value["source"]["owner_oid"] for row in objects),
            "SOURCE_REPLAY_OBJECT_OWNER",
        )
        row = connection.execute(
            "SELECT pg_catalog.pg_backend_pid() AS pid,extract(epoch FROM backend_start)::text AS generation "
            "FROM pg_catalog.pg_stat_activity WHERE pid=pg_catalog.pg_backend_pid()"
        ).fetchone()
        return dict(row, database_oid=value["source"]["database_oid"], owner_oid=value["source"]["owner_oid"])


def _event(value: Any, event: str, **details: Any) -> dict[str, Any]:
    return dict(event=event, nonce=value["nonce"], request_sha256=digest(value), **details)


def _emit(value: Any) -> None:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    require(len(raw) <= 65536, "SOURCE_REPLAY_PROTOCOL_LENGTH")
    print(raw, flush=True)


def _ack(expected: Any) -> None:
    raw = sys.stdin.readline(65537)
    require(len(raw) <= 65536 and raw.endswith("\n"), "SOURCE_REPLAY_ACK_INVALID")
    require(json.loads(raw) == expected, "SOURCE_REPLAY_ACK_INVALID")


def _read_only(repo: Any, enabled: bool) -> None:
    with repo.pool.connection() as connection:
        connection.execute("SET default_transaction_read_only=" + ("on" if enabled else "off"))


def _prefer(first: BaseException | None, later: BaseException | None) -> BaseException | None:
    if isinstance(first, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return first
    if isinstance(later, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return later
    return first if first is not None else later


def _leased(value: Any, repo: Any, lease: Any, pool: Any, deployment: Any, monotone: Any, audit: Any) -> None:
    original = load_control(value, "first_release_replay_effects.py")
    effects = load_control(value, "first_release_source_effects.py")
    projection = load_control(value, "first_release_incremental_pg.py")["snapshot"]
    peer = _source(repo, value)
    before = effects["state"](repo, projection)
    effects["central"](repo, before, require)
    audit()
    ready = _event(value, "ready_ro", **peer, state_sha256=digest(before))
    _emit(ready)
    _ack(dict(ready, event="write_ack"))
    pool["require_idle_lease"](lease)
    audit()
    _read_only(repo, False)
    seen: list[str] = []

    def phase(name: str) -> None:
        require(len(seen) < len(PHASES) and name == PHASES[len(seen)], "SOURCE_REPLAY_PHASE_ORDER")
        seen.append(name)
        pool["require_idle_lease"](lease)
        _emit(_event(value, "phase", phase=name))

    result = effects["replay_source"](
        value, repo, deployment, monotone, original, projection, audit, phase, require, ready["state_sha256"]
    )
    _read_only(repo, True)
    require(_source(repo, value) == peer and seen == list(PHASES), "SOURCE_REPLAY_SOURCE_CHANGED")
    require(
        digest(effects["state"](repo, projection)) == result["state_second_sha256"], "SOURCE_REPLAY_FINAL_STATE_CHANGED"
    )
    physical = pool["lease_identity"](lease)
    audit()
    _emit(_event(value, "final_live", **peer, **result, physical_connections=physical["physical_connections"]))
    _ack(_event(value, "done_ack", pid=peer["pid"], state_sha256=result["state_second_sha256"]))
    # The parent observed this same live lease. No mutations or replacement checkout follow its ACK.
    pool["require_idle_lease"](lease)
    require(
        digest(effects["state"](repo, projection)) == result["state_second_sha256"], "SOURCE_REPLAY_FINAL_STATE_CHANGED"
    )
    audit()


def run(value: Any) -> None:
    _admit(value)
    foundation = load_control(value, "first_release_replay_worker.py")
    repository, deployment, monotone, audit, _ = _candidate(value, foundation)
    pool = load_control(value, "first_release_source_pool.py")
    repo, expected = _repository(value, repository, pool)
    failure = None
    try:
        with pool["pinned_candidate_pool"](repo, expected) as lease:
            _leased(value, repo, lease, pool, deployment, monotone, audit)
    except BaseException as error:
        failure = error
    try:
        repo.close()
    except BaseException as error:
        failure = _prefer(failure, error)
    if failure is not None:
        raise failure
    _emit(_event(value, "closed"))


if __name__ == "__main__":
    try:
        run(globals().get("_SOURCE_INPUT"))
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException:
        # Even dependency/native exceptions can carry private data. The parent retains its last phase.
        _emit({"event": "blocked", "code": "SOURCE_REPLAY_WORKER_REJECTED"})
        raise SystemExit(2) from None
