"""Stdlib bootstrap for candidate-native backfill; source authority stays in the live parent."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import runpy
import sys
from pathlib import Path
from typing import Any

HELPERS = ("first_release_backfill_effects", "first_release_backfill_expected")
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


class Blocked(BaseException):
    """Finite control stops escape candidate ordinary-exception handlers."""


def require(value: Any, code: str) -> None:
    if not value:
        raise Blocked(code)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _fields() -> tuple[set[str], set[str]]:
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
    pins = {
        "binding_sha256",
        "forward_pin_sha256",
        "replay_pin_sha256",
        "candidate",
        "manifest_sha256",
        "locks",
        "ledger_sha256",
        "python_sha256",
        "controls",
    }
    return fields, pins


def _admit(value: Any) -> dict[str, Any]:
    fields, pins = _fields()
    require(
        type(value) is dict
        and set(value) == fields
        and value["local_drill"] is True
        and value["schema"] == "first-release-local-source-backfill-worker-v1",
        "SOURCE_BACKFILL_LOCAL_INPUT",
    )
    pin = value["pin"]
    require(
        type(pin) is dict
        and set(pin) == pins
        and all(
            type(pin[key]) is str and re.fullmatch(r"[0-9a-f]{64}", pin[key]) for key in pins if key.endswith("sha256")
        )
        and type(pin["candidate"]) is str
        and re.fullmatch(r"[0-9a-f]{40}", pin["candidate"]),
        "SOURCE_BACKFILL_PIN_FIELDS",
    )
    require(
        type(value["operation_id"]) is str
        and re.fullmatch(r"fr-[0-9a-f]{32}", value["operation_id"])
        and value["source"]["database"] == "fr_upgrade_" + value["operation_id"][3:]
        and type(value["parent_pid"]) is int
        and value["parent_pid"] > 0
        and type(value["nonce"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", value["nonce"]),
        "SOURCE_BACKFILL_SOURCE_IDENTITY",
    )
    require(
        not any(name.split(".")[0] in {"tools", "mingjing_core"} for name in sys.modules),
        "SOURCE_BACKFILL_PRELOADED_BUSINESS",
    )
    require(
        Path(value["worker"]) == Path(value["control_root"]) / "tools/first_release_source_backfill_worker.py",
        "SOURCE_BACKFILL_WORKER_ORIGIN",
    )
    path = Path(value["control_root"]) / "tools/first_release_source_worker.py"
    require(
        path.is_absolute()
        and path.is_file()
        and not any(p.is_symlink() for p in (path, *path.parents))
        and hashlib.sha256(path.read_bytes()).hexdigest() == value["controls"]["tools/first_release_source_worker.py"],
        "SOURCE_BACKFILL_BASE_CHANGED",
    )
    base = runpy.run_path(str(path), run_name="__reviewed_source_backfill_base")
    base["checked_controls"](value)
    return base


def _functions(modules: list[Any], memory: Any, tokenized: Any, fingerprint: Any) -> list[Any]:
    functions = [memory.__init__, tokenized, fingerprint]
    for module in modules:
        functions.extend(
            item
            for item in vars(module).values()
            if hasattr(item, "__code__") and getattr(item, "__module__", "").split(".")[0] in {"tools", "mingjing_core"}
        )
    return functions


def _native(value: Any, foundation: Any, repository: Any, prior_audit: Any) -> tuple[Any, Any, Any]:
    root = Path(value["root"])
    manifest = root / "__release_manifest__.json"
    files = json.loads(manifest.read_bytes())["files"]
    memory = importlib.import_module("mingjing_core.application.memory").MemoryService
    module = importlib.import_module("mingjing_core.memory.backfill")
    projections = importlib.import_module("mingjing_core.memory.projections")
    effects, expected = [importlib.import_module("tools." + name) for name in HELPERS]
    functions = _functions([module, effects, expected], memory, projections.tokenized_payload, repository.fingerprint)

    def audit() -> None:
        prior_audit()
        for name in HELPERS:
            relative = "tools/" + name + ".py"
            require(
                relative in files and files[relative]["sha256"] == value["controls"][relative],
                "SOURCE_BACKFILL_CANDIDATE_HELPER_PIN",
            )
            foundation["verified"](str(root / relative), root, files)
        for function in functions:
            foundation["verified"](function.__code__.co_filename, root, files)
        foundation["business_origins"](root, files)

    audit()
    bindings = expected.BackfillBindings(memory, module, projections.tokenized_payload, repository.fingerprint)
    return effects, bindings, audit


def _state(repo: Any, projection: Any) -> dict[str, Any]:
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        return projection(connection)


def _event(value: Any, event: str, **details: Any) -> dict[str, Any]:
    return dict(event=event, nonce=value["nonce"], request_sha256=digest(value), **details)


def _accumulate(totals: dict, result: Any) -> None:
    require(type(result) is dict, "SOURCE_BACKFILL_COMPONENT_RESULT")
    require(
        all(result.get(name) is True for name in ("metadata_values_verified", "generated_search_verified")),
        "SOURCE_BACKFILL_COMPONENT_RESULT",
    )
    for stage in ("preview", "first", "second"):
        row = result.get(stage)
        require(
            type(row) is dict
            and set(row) == COUNTS
            and all(type(item) is int and 0 <= item < 2**63 for item in row.values()),
            "SOURCE_BACKFILL_COMPONENT_COUNTS",
        )
        for name, item in row.items():
            totals[stage][name] += item
            require(totals[stage][name] < 2**63, "SOURCE_BACKFILL_COMPONENT_COUNTS")
    require(
        all(result["second"][key] == 0 for key in ("message_metadata", "search_tokens", "assistant_created")),
        "SOURCE_BACKFILL_SECOND_WRITES",
    )


def _owners(
    value: Any, repo: Any, lease: Any, pool: Any, base: Any, native: Any, projection: Any, initial: str
) -> dict[str, Any]:
    effects, bindings, audit = native
    totals = {stage: dict.fromkeys(sorted(COUNTS), 0) for stage in ("preview", "first", "second")}
    records, expected_state = [], initial
    for index, owner in enumerate(value["source"]["owners"], 1):
        pool["require_idle_lease"](lease)
        audit()
        base["_emit"](_event(value, "phase", index=index, owner_sha256=digest(owner), phase="owner_started"))
        # Only this owner's backfill is enclosed; privacy commits and purge remain outside it.
        with repo.transaction(owner) as connection:
            connection.execute("SET LOCAL TimeZone='UTC'")
            connection.execute("SET LOCAL search_path=pg_catalog")
            require(digest(projection(connection)) == expected_state, "SOURCE_BACKFILL_OWNER_STATE_CHANGED")
            result = effects.verify_backfill_effects(repo, owner, bindings=bindings)
            expected_state = digest(projection(connection))
        pool["require_idle_lease"](lease)
        audit()
        _accumulate(totals, result)
        records.append(digest(result))
        base["_emit"](_event(value, "phase", index=index, owner_sha256=digest(owner), phase="owner_verified"))
    return dict(
        **totals,
        owners_processed=len(records),
        owners_sha256=digest(value["source"]["owners"]),
        owner_results_sha256=digest(records),
        all_owners_verified=True,
        state_after_sha256=expected_state,
    )


def _leased(value: Any, repo: Any, lease: Any, pool: Any, base: Any, native: Any) -> None:
    _, _, audit = native
    observations = base["load_control"](value, "first_release_source_effects.py")
    projection = base["load_control"](value, "first_release_incremental_pg.py")["snapshot"]
    peer = base["_source"](repo, value)
    before = _state(repo, projection)
    quota = observations["central"](repo, before, require)
    audit()
    ready = _event(value, "ready_ro", **peer, state_sha256=digest(before))
    base["_emit"](ready)
    base["_ack"](dict(ready, event="write_ack"))
    pool["require_idle_lease"](lease)
    audit()
    require(base["_source"](repo, value) == peer, "SOURCE_BACKFILL_SOURCE_CHANGED")
    require(digest(_state(repo, projection)) == ready["state_sha256"], "SOURCE_BACKFILL_INITIAL_STATE_CHANGED")
    base["_read_only"](repo, False)
    result = _owners(value, repo, lease, pool, base, native, projection, ready["state_sha256"])
    base["_read_only"](repo, True)
    require(base["_source"](repo, value) == peer, "SOURCE_BACKFILL_SOURCE_CHANGED")
    after = _state(repo, projection)
    require(digest(after) == result["state_after_sha256"], "SOURCE_BACKFILL_FINAL_STATE_CHANGED")
    require(observations["central"](repo, after, require) == quota, "SOURCE_BACKFILL_CENTRAL_CHANGED")
    result.update(state_before_sha256=ready["state_sha256"], central_unchanged=True)
    physical = pool["lease_identity"](lease)
    audit()
    base["_emit"](_event(value, "final_live", **peer, **result, physical_connections=physical["physical_connections"]))
    base["_ack"](_event(value, "done_ack", pid=peer["pid"], state_sha256=result["state_after_sha256"]))
    pool["require_idle_lease"](lease)
    require(digest(_state(repo, projection)) == result["state_after_sha256"], "SOURCE_BACKFILL_FINAL_STATE_CHANGED")
    audit()


def run(value: Any) -> None:
    base = _admit(value)
    foundation = base["load_control"](value, "first_release_replay_worker.py")
    repository, _, _, audit, _ = base["_candidate"](value, foundation)
    native = _native(value, foundation, repository, audit)
    pool = base["load_control"](value, "first_release_source_pool.py")
    repo, expected = base["_repository"](value, repository, pool)
    failure = None
    try:
        with pool["pinned_candidate_pool"](repo, expected) as lease:
            _leased(value, repo, lease, pool, base, native)
    except BaseException as error:
        failure = error
    try:
        repo.close()
    except BaseException as error:
        failure = base["_prefer"](failure, error)
    if failure is not None:
        raise failure
    base["_emit"](_event(value, "closed"))


if __name__ == "__main__":
    try:
        run(globals().get("_SOURCE_BACKFILL_INPUT"))
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException:
        # No native exception, private identifier, or body is copied to the protocol.
        print(json.dumps({"event": "blocked", "code": "SOURCE_BACKFILL_WORKER_REJECTED"}), flush=True)
        raise SystemExit(2) from None
