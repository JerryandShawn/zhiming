"""Explicit same-call source replay, requiring live forward authority and a separate reviewed pin."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools import first_release_incremental_scope as scopes
from tools.first_release_candidate_process import _environment
from tools.first_release_contracts import RestoreRejected, digest, ordinary, require
from tools.first_release_incremental import file_hash
from tools.first_release_incremental_forward import ForwardInputs
from tools.first_release_incremental_pg import sessions, snapshot
from tools.first_release_source_protocol import cleanup as _cleanup
from tools.first_release_source_protocol import prefer as _prefer
from tools.first_release_source_protocol import read as _read
from tools.first_release_source_protocol import send as _send

ROOT = Path(__file__).parent.parent
WORKER = ROOT / "tools/first_release_source_worker.py"
DIRECT = frozenset(
    "tools/" + name
    for name in (
        "first_release_source_process.py",
        "first_release_source_worker.py",
        "first_release_source_effects.py",
        "first_release_source_pool.py",
        "first_release_source_protocol.py",
        "first_release_replay_worker.py",
        "first_release_replay_effects.py",
        "first_release_incremental_pg.py",
    )
)
PHASES = (
    "first_apply_started",
    "first_native_completed",
    "first_verified",
    "second_apply_started",
    "second_native_completed",
    "second_verified",
)
BOOTSTRAP = """import hashlib,json,pathlib,runpy,sys
value=json.loads(sys.stdin.readline(65537))
path=pathlib.Path(value['worker'])
if hashlib.sha256(path.read_bytes()).hexdigest()!=value['controls']['tools/first_release_source_worker.py']:
    raise SystemExit(2)
runpy.run_path(str(path),run_name='__main__',init_globals={'_SOURCE_INPUT':value})
"""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def controls(request: ForwardInputs) -> dict[str, str]:
    """All inherited control pins remain separate, and must agree rather than overwrite each other."""
    inherited = [request.pin.controls, request.target_pin.controls]
    inherited += [
        tuple(("tools/" + name, sha) for name, sha in rows)
        for rows in (
            request.source.controls,
            request.capture.pin.controls,
        )
    ]
    result: dict[str, str] = {}
    for rows in inherited:
        for name, sha in rows:
            require(name not in result or result[name] == sha, "SOURCE_REPLAY_INHERITED_CONTROL_MISMATCH")
            result[name] = sha
    for name in DIRECT:
        sha = file_hash(ROOT / name)
        require(name not in result or result[name] == sha, "SOURCE_REPLAY_INHERITED_CONTROL_MISMATCH")
        result[name] = sha
    return result


@dataclass(frozen=True)
class SourceReplayPin:
    binding_sha256: str
    forward_pin_sha256: str
    candidate: str
    manifest_sha256: str
    locks: tuple[tuple[str, str], ...]
    ledger_sha256: str
    python_sha256: str
    controls: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> SourceReplayPin:
        names = set(cls.__dataclass_fields__)
        require(
            type(value) is dict
            and set(value) == names | {"schema"}
            and value["schema"] == "first-release-local-source-replay-pin-v1"
            and type(value["controls"]) is dict
            and type(value["locks"]) is dict,
            "SOURCE_REPLAY_PIN_FIELDS",
        )
        return cls(
            **{name: value[name] for name in names - {"controls", "locks"}},
            controls=tuple(sorted(value["controls"].items())),
            locks=tuple(sorted(value["locks"].items())),
        )

    def validate(self, request: ForwardInputs) -> None:
        require(type(self) is SourceReplayPin and type(request) is ForwardInputs, "SOURCE_REPLAY_TYPED_PIN")
        request.validate()
        require(
            all(digest(getattr(self, name)) for name in self.__dataclass_fields__ if name.endswith("sha256"))
            and digest(self.candidate, 40),
            "SOURCE_REPLAY_PIN_DIGEST",
        )
        require(
            type(self.controls) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.controls)
            and type(self.locks) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.locks)
            and self.controls == tuple(sorted(controls(request).items()))
            and self.locks == tuple(sorted(request.source.release.locks)),
            "SOURCE_REPLAY_CONTROL_SET",
        )
        require(
            (self.binding_sha256, self.forward_pin_sha256, self.candidate, self.manifest_sha256, self.python_sha256)
            == (
                request.pin.binding_sha256,
                _digest(asdict(request.pin)),
                request.source.release.candidate,
                request.source.release.manifest_sha256,
                request.source.python_sha256,
            ),
            "SOURCE_REPLAY_REVIEW_BINDING",
        )
        require(self.ledger_sha256 == request.capture.pin.ledger_sha256, "SOURCE_REPLAY_LEDGER_BINDING")
        ledger = request.source.operation_dir / "latest-withdrawals.json"
        for path, sha in [(ROOT / name, sha) for name, sha in self.controls] + [(ledger, self.ledger_sha256)]:
            ordinary(path)
            require(digest(sha) and file_hash(path) == sha, "SOURCE_REPLAY_REVIEWED_FILE_CHANGED")


class SourceReplayStopped(RestoreRejected):
    def __init__(self, code: str, phase: str) -> None:
        super().__init__(code if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) else "SOURCE_REPLAY_STOPPED")
        self.phase, self.automatic_cleanup = phase, False
        self.native_commit_may_have_completed = phase not in {"source_replay_preflight", "ready_ro"}


def _payload(request: ForwardInputs, pin: SourceReplayPin, parent_pid: int) -> dict[str, Any]:
    pin.validate(request)
    source = request.source
    identity = dict(asdict(source.source), owners=list(source.source.owners), migrations=dict(source.source.migrations))
    return dict(
        schema="first-release-local-source-worker-v1",
        local_drill=True,
        worker=str(WORKER),
        control_root=str(ROOT),
        controls=dict(pin.controls),
        root=str(source.candidate_source),
        python=str(source.python),
        pin=asdict(pin),
        source=identity,
        operation_id=source.operation_id,
        parent_pid=parent_pid,
        nonce=secrets.token_hex(32),
        core_lock_sha256=dict(source.release.locks)["requirements-core.lock"],
        migrations=dict(source.release.migrations),
        replay={"ledger": str(source.operation_dir / "latest-withdrawals.json")},
    )


def _peer(parent: Any, payload: Any, value: Any) -> None:
    source = payload["source"]
    require(
        type(value.get("pid")) is int and value["pid"] > 0 and value["pid"] != parent.info.backend_pid,
        "SOURCE_REPLAY_PEER_PID",
    )
    sessions(parent, {parent.info.backend_pid, value["pid"]})
    row = parent.execute(
        "SELECT datid,usesysid,extract(epoch FROM backend_start)::text AS generation "
        "FROM pg_catalog.pg_stat_activity WHERE pid=%s",
        (value["pid"],),
    ).fetchone()
    require(
        row == {"datid": source["database_oid"], "usesysid": source["owner_oid"], "generation": value["generation"]}
        and value["database_oid"] == source["database_oid"]
        and value["owner_oid"] == source["owner_oid"],
        "SOURCE_REPLAY_ACTUAL_PEER_CHANGED",
    )


def _state(parent: Any) -> str:
    with parent.transaction():
        parent.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        parent.execute("SET LOCAL search_path=pg_catalog")
        return _digest(snapshot(parent))


def _bound(payload: Any, value: Any, event: str) -> None:
    require(
        value.get("event") == event
        and value.get("nonce") == payload["nonce"]
        and value.get("request_sha256") == _digest(payload),
        "SOURCE_REPLAY_PROTOCOL_BINDING",
    )


def _result(payload: Any, value: Any) -> None:
    identity = {"event", "nonce", "request_sha256", "pid", "generation", "database_oid", "owner_oid"}
    hashes = {
        "state_before_sha256",
        "state_first_sha256",
        "state_second_sha256",
        "export_first_sha256",
        "export_second_sha256",
    }
    flags = {"second_apply_unchanged", "central_unchanged"}
    require(
        set(value) == identity | hashes | flags | {"first_counts", "second_counts", "checks", "physical_connections"}
        and all(digest(value[name]) for name in hashes)
        and all(value[name] is True for name in flags)
        and value["state_first_sha256"] == value["state_second_sha256"]
        and value["export_first_sha256"] == value["export_second_sha256"]
        and type(value["physical_connections"]) is int
        and value["physical_connections"] == 1,
        "SOURCE_REPLAY_RESULT_FIELDS",
    )
    for key in ("first_counts", "second_counts", "checks"):
        values = value[key]
        require(
            type(values) is dict
            and len(values) <= 32
            and all(
                re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) and type(item) is int and 0 <= item < 2**63
                for name, item in values.items()
            ),
            "SOURCE_REPLAY_RESULT_COUNTS",
        )
    require(
        all(
            value[key].get(name) == 0
            for key in ("first_counts", "second_counts")
            for name in ("model_calls", "external_sends")
        ),
        "SOURCE_REPLAY_EXTERNAL_EFFECTS",
    )
    _bound(payload, value, "final_live")


def _protocol(process: Any, payload: Any, ready: Any, final: Any, phase: Any) -> dict[str, Any]:
    deadline = time.monotonic() + 120
    _send(process, payload)
    hello = _read(process, deadline)
    _bound(payload, hello, "ready_ro")
    require(
        set(hello)
        == {"event", "nonce", "request_sha256", "pid", "generation", "database_oid", "owner_oid", "state_sha256"}
        and digest(hello["state_sha256"]),
        "SOURCE_REPLAY_READY_FIELDS",
    )
    ready(hello)
    _send(process, dict(hello, event="write_ack"))
    for expected in PHASES:
        value = _read(process, deadline)
        _bound(payload, value, "phase")
        require(
            set(value) == {"event", "nonce", "request_sha256", "phase"} and value["phase"] == expected,
            "SOURCE_REPLAY_PHASE_ORDER",
        )
        phase(expected)
    result = _read(process, deadline)
    _result(payload, result)
    require(result["state_before_sha256"] == hello["state_sha256"], "SOURCE_REPLAY_INITIAL_STATE_CHANGED")
    require(
        all(result[key] == hello[key] for key in ("pid", "generation", "database_oid", "owner_oid")),
        "SOURCE_REPLAY_PEER_CHANGED",
    )
    final(result)
    _send(
        process,
        {
            "event": "done_ack",
            "nonce": payload["nonce"],
            "request_sha256": _digest(payload),
            "pid": result["pid"],
            "state_sha256": result["state_second_sha256"],
        },
    )
    closed = _read(process, deadline)
    _bound(payload, closed, "closed")
    require(set(closed) == {"event", "nonce", "request_sha256"}, "SOURCE_REPLAY_CLOSE_FIELDS")
    process.wait(timeout=max(0.01, deadline - time.monotonic()))
    require(process.returncode == 0 and process.stdout.read(65537) == "", "SOURCE_REPLAY_PROCESS_FAILED")
    return result


def _exchange(payload: Any, python: Path, dsn: str, ready: Any, final: Any, phase: Any) -> dict[str, Any]:
    """Private transport seam; production authority is exclusively checked by source_replay."""
    env = _environment("")
    env.pop("FIRST_RELEASE_CANDIDATE_OWNER_DSN")
    env["FIRST_RELEASE_SOURCE_OWNER_DSN"] = dsn
    process = subprocess.Popen(
        [str(python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", BOOTSTRAP],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    failure, result = None, None
    try:
        result = _protocol(process, payload, ready, final, phase)
    except BaseException as error:
        failure = error
    failure = _prefer(failure, _cleanup(process))
    if failure is not None:
        raise failure
    require(result is not None, "SOURCE_REPLAY_RESULT_REQUIRED")
    return result


def source_replay(witness: scopes.SourceUpgradeWitness, pin: SourceReplayPin) -> dict[str, Any]:
    authority = scopes._active(witness, "source_forward_completed")
    scope, request = authority.scope, authority.scope.request
    require(type(pin) is SourceReplayPin, "SOURCE_REPLAY_TYPED_PIN")
    payload = _payload(request, pin, scope.pid)
    scope.phase = "source_replay_preflight"

    def current(value: Any) -> None:
        scopes._active(witness, scope.phase)
        pin.validate(request)
        _peer(scope.owner, payload, value)

    def ready(value: Any) -> None:
        current(value)
        require(_state(scope.owner) == value["state_sha256"], "SOURCE_REPLAY_READY_STATE_CHANGED")
        scope.phase = "ready_ro"

    def final(value: Any) -> None:
        current(value)
        require(_state(scope.owner) == value["state_second_sha256"], "SOURCE_REPLAY_FINAL_STATE_CHANGED")

    try:
        result = _exchange(
            payload,
            request.source.python,
            scope.dsns["owner"],
            ready,
            final,
            lambda value: setattr(scope, "phase", value),
        )
        scopes._active(witness, scope.phase)
        pin.validate(request)
        sessions(scope.owner, {scope.pid})
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except Exception as error:
        code = str(error) if isinstance(error, RestoreRejected) else "SOURCE_REPLAY_PROCESS_STOPPED"
        raise SourceReplayStopped(code, scope.phase) from None
    scope.phase = "source_replay_completed"
    return dict(
        result,
        schema="first-release-local-source-replay-v1",
        source_operation_id=request.source.operation_id,
        candidate=pin.candidate,
        source_replay_completed=True,
        parent_final_state_verified=True,
        maintenance_retained=True,
        privacy_replay_pending=False,
        backfill_pending=True,
        source_upgraded=False,
        source_write_authorized=False,
        runtime_verified=False,
        native_restore_completed=False,
        central_binding_verified=False,
        global_quiescence_verified=False,
        linux_attestation=False,
        publication=False,
        model_calls=0,
        external_sends=0,
    )
