"""Same-call backfill admission and bounded owned-child protocol; no reusable JSON authority."""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools import first_release_incremental_scope as scopes
from tools.first_release_candidate_process import _environment
from tools.first_release_contracts import RestoreRejected, digest, require
from tools.first_release_incremental_pg import sessions
from tools.first_release_source_backfill_pin import ROOT, SourceBackfillPin
from tools.first_release_source_process import SourceReplayPin, _bound, _digest, _peer, _state
from tools.first_release_source_protocol import cleanup, prefer, read, send

WORKER = ROOT / "tools/first_release_source_backfill_worker.py"
COUNTS = frozenset(
    {
        "message_metadata",
        "search_tokens",
        "invalid_time",
        "assistant_created",
        "assistant_existing",
        "assistant_skipped",
    }
)
BOOTSTRAP = """import hashlib,json,pathlib,runpy,sys
value=json.loads(sys.stdin.readline(65537))
path=pathlib.Path(value['worker'])
if hashlib.sha256(path.read_bytes()).hexdigest()!=value['controls']['tools/first_release_source_backfill_worker.py']:
    raise SystemExit(2)
runpy.run_path(str(path),run_name='__main__',init_globals={'_SOURCE_BACKFILL_INPUT':value})
"""


class SourceBackfillStopped(RestoreRejected):
    def __init__(self, code: str, phase: str) -> None:
        super().__init__(code if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) else "SOURCE_BACKFILL_STOPPED")
        self.phase, self.automatic_cleanup = phase, False
        self.native_commit_may_have_completed = phase not in {"source_backfill_preflight", "backfill_ready_ro"}


def _payload(request: Any, pin: SourceBackfillPin, replay_pin: SourceReplayPin, parent_pid: int) -> dict[str, Any]:
    pin.validate(request, replay_pin)
    source = request.source
    identity = dict(asdict(source.source), owners=list(source.source.owners), migrations=dict(source.source.migrations))
    return dict(
        schema="first-release-local-source-backfill-worker-v1",
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


def _ready_fields(payload: Any, value: Any) -> None:
    _bound(payload, value, "ready_ro")
    require(
        set(value)
        == {"event", "nonce", "request_sha256", "pid", "generation", "database_oid", "owner_oid", "state_sha256"}
        and digest(value["state_sha256"]),
        "SOURCE_BACKFILL_READY_FIELDS",
    )


def _result(payload: Any, value: Any) -> None:
    identity = {"event", "nonce", "request_sha256", "pid", "generation", "database_oid", "owner_oid"}
    hashes = {"state_before_sha256", "state_after_sha256", "owners_sha256", "owner_results_sha256"}
    counts = {"preview", "first", "second"}
    flags = {"all_owners_verified", "central_unchanged"}
    require(
        set(value) == identity | hashes | counts | flags | {"owners_processed", "physical_connections"}
        and all(digest(value[name]) for name in hashes)
        and all(value[name] is True for name in flags)
        and type(value["owners_processed"]) is int
        and value["owners_processed"] == len(payload["source"]["owners"])
        and value["owners_sha256"] == _digest(payload["source"]["owners"])
        and type(value["physical_connections"]) is int
        and value["physical_connections"] == 1,
        "SOURCE_BACKFILL_RESULT_FIELDS",
    )
    for key in counts:
        items = value[key]
        require(
            type(items) is dict
            and set(items) == COUNTS
            and all(type(item) is int and 0 <= item < 2**63 for item in items.values()),
            "SOURCE_BACKFILL_RESULT_COUNTS",
        )
    require(
        all(value["second"][key] == 0 for key in ("message_metadata", "search_tokens", "assistant_created")),
        "SOURCE_BACKFILL_SECOND_WRITES",
    )
    _bound(payload, value, "final_live")


def _owners(process: Any, payload: Any, deadline: float, phase: Any) -> None:
    fields = {"event", "nonce", "request_sha256", "index", "owner_sha256", "phase"}
    for index, owner in enumerate(payload["source"]["owners"], 1):
        for expected in ("owner_started", "owner_verified"):
            value = read(process, deadline)
            _bound(payload, value, "phase")
            require(
                set(value) == fields
                and type(value["index"]) is int
                and value["index"] == index
                and value["owner_sha256"] == _digest(owner)
                and value["phase"] == expected,
                "SOURCE_BACKFILL_OWNER_ORDER",
            )
            phase(f"source_backfill_{index}_{expected}")


def _protocol(process: Any, payload: Any, ready: Any, final: Any, phase: Any) -> dict[str, Any]:
    deadline = time.monotonic() + 120
    send(process, payload)
    hello = read(process, deadline)
    _ready_fields(payload, hello)
    ready(hello)
    send(process, dict(hello, event="write_ack"))
    _owners(process, payload, deadline, phase)
    result = read(process, deadline)
    _result(payload, result)
    require(result["state_before_sha256"] == hello["state_sha256"], "SOURCE_BACKFILL_INITIAL_STATE_CHANGED")
    require(
        all(result[key] == hello[key] for key in ("pid", "generation", "database_oid", "owner_oid")),
        "SOURCE_BACKFILL_PEER_CHANGED",
    )
    final(result)
    send(
        process,
        dict(
            event="done_ack",
            nonce=payload["nonce"],
            request_sha256=_digest(payload),
            pid=result["pid"],
            state_sha256=result["state_after_sha256"],
        ),
    )
    closed = read(process, deadline)
    _bound(payload, closed, "closed")
    require(set(closed) == {"event", "nonce", "request_sha256"}, "SOURCE_BACKFILL_CLOSE_FIELDS")
    process.wait(timeout=max(0.01, deadline - time.monotonic()))
    require(process.returncode == 0 and process.stdout.read(65537) == "", "SOURCE_BACKFILL_PROCESS_FAILED")
    return result


def _exchange(payload: Any, python: Path, dsn: str, ready: Any, final: Any, phase: Any) -> dict[str, Any]:
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
    failure = prefer(failure, cleanup(process))
    if failure is not None:
        raise failure
    require(result is not None, "SOURCE_BACKFILL_RESULT_REQUIRED")
    return result


def source_backfill(witness: scopes.SourceUpgradeWitness, pin: SourceBackfillPin, replay_pin: SourceReplayPin) -> dict:
    authority = scopes._active(witness, "source_replay_completed")
    scope, request = authority.scope, authority.scope.request
    require(type(pin) is SourceBackfillPin and type(replay_pin) is SourceReplayPin, "SOURCE_BACKFILL_TYPED_PIN")
    payload = _payload(request, pin, replay_pin, scope.pid)
    scope.phase = "source_backfill_preflight"

    def current(value: Any) -> None:
        scopes._active(witness, scope.phase)
        pin.validate(request, replay_pin)
        _peer(scope.owner, payload, value)

    def ready(value: Any) -> None:
        current(value)
        require(_state(scope.owner) == value["state_sha256"], "SOURCE_BACKFILL_READY_STATE_CHANGED")
        scope.phase = "backfill_ready_ro"

    def final(value: Any) -> None:
        current(value)
        require(_state(scope.owner) == value["state_after_sha256"], "SOURCE_BACKFILL_FINAL_STATE_CHANGED")

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
        pin.validate(request, replay_pin)
        sessions(scope.owner, {scope.pid})
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except Exception as error:
        code = str(error) if isinstance(error, RestoreRejected) else "SOURCE_BACKFILL_PROCESS_STOPPED"
        raise SourceBackfillStopped(code, scope.phase) from None
    scope.phase = "source_backfill_completed"
    return dict(
        result,
        schema="first-release-local-source-backfill-v1",
        source_operation_id=request.source.operation_id,
        candidate=pin.candidate,
        source_backfill_completed=True,
        parent_final_state_verified=True,
        maintenance_retained=True,
        privacy_replay_pending=False,
        backfill_pending=False,
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
