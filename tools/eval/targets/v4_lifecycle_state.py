"""Private evaluator state and native run/source checks; no business effects are replayed."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import FrozenClock, get_clock
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.providers.scripted import ScriptedProvider

from .v4_memory_lifecycle_state import restore_memory, snapshot_memory
from .v4_privacy_seed import V4PrivacySeeder
from .v4_tarot import TarotDriver

STAGE = "eval_lifecycle"
FORMAT = "eval-scenario-private-v1"
SEEDER_FIELDS = ("ids", "case_ids", "profile_fact_ids", "privacy_layers", "privacy_aliases")
TARGET_FIELDS = (
    "seed",
    "bindings",
    "run_ids",
    "cancellation",
    "portability",
    "semantic",
    "semantic_history",
    "crashed_run",
    "privacy_initial",
)


def source_identity(repo: PostgresRepository, owner: str, ident: str, thread: str) -> dict[str, Any]:
    source = MemoryService(repo).get_source(owner, ident, for_context=True)
    if (
        source.get("role") != "user"
        or source.get("thread_id") != thread
        or source["status"] != "active"
        or source.get("policy", {}).get("origin") != "current_user"
        or source.get("policy", {}).get("run_context") is not True
        or repo.is_revoked(owner, "message", ident)
    ):
        raise LifecycleError("评测原话已失效")
    return {
        "id": ident,
        "revision": source["revision"],
        "sha256": fingerprint(
            {
                key: source.get(key)
                for key in ("content", "role", "thread_id", "subject_id", "channel", "policy", "at_ms", "source_id")
            }
        ),
    }


def run_identity(repo: PostgresRepository, owner: str, ident: str, *, current: bool) -> dict[str, Any]:
    run = repo.fetch_run(owner, ident)
    allowed = {"queued", "running"} if current else {"succeeded"}
    if run["runtime"] != "v4" or run["status"] not in allowed or run["cancel_requested_at"] is not None:
        raise LifecycleError("评测运行已终止或取消")
    thread = assert_thread(repo, run)
    if not repo.verify_versions(owner, run["state_version"]):
        raise LifecycleError("评测依赖已经改变")
    sources = run["request"].get("source_message_ids", [run["request"]["source_message_id"]])
    originals = [source_identity(repo, owner, source, thread) for source in sources]
    first = MemoryService(repo).get_source(owner, run["request"]["source_message_id"], for_context=True)
    if first.get("content") != run["request"].get("message"):
        raise LifecycleError("评测原话与运行请求不符")
    return {
        "id": ident,
        "epoch": run["retry_epoch"],
        "subject": run["subject"],
        "thread": thread,
        "request_sha256": fingerprint(run["request"]),
        "dependencies_sha256": fingerprint(run["state_version"]),
        "result_sha256": fingerprint(run["result"]),
        "sources": originals,
    }


def validate_seed(seed: dict[str, Any], binding: LifecycleBinding) -> None:
    from tools.eval.targets.v4_core30 import load_core30

    case = next(case for case in load_core30() if case.id == binding.scenario_id)
    expected = case.seed.model_dump(mode="json")
    expected.update(
        _scenario_id=case.id,
        _clock=case.clock,
        _scripted=[step.model_dump(exclude_none=True) for step in case.scripted],
    )
    if seed != expected or seed.get("synthetic") is not True:
        raise LifecycleError("私密场景种子与固定契约不符")


def snapshot(target: Any, binding: LifecycleBinding, turn: int, completed: dict | None = None) -> dict[str, Any]:
    from .v4_execution_budget_store import closed_budgets

    validate_seed(target.seed, binding)
    if (
        target.repo is None
        or not target.run_ids
        or target.feishu is not None
        or type(turn) is not int
        or turn < 1
        or "turn-" + str(turn) not in target.bindings
    ):
        raise LifecycleError("本片仅保存已绑定原话的本机core30运行")
    records = [
        run_identity(target.repo, target.owner, ident, current=completed is None and index == len(target.run_ids) - 1)
        for index, ident in enumerate(target.run_ids)
    ]
    if records[-1]["thread"] != target.thread["id"]:
        raise LifecycleError("评测线程与运行不一致")
    budgets = closed_budgets(target, binding, required=target._budget_started)
    return {
        "format": FORMAT,
        "owner": target.owner,
        "model": target.model,
        "turn": turn,
        "phase": "primary_complete" if completed is not None else "primary_pending",
        "completed_turn": completed,
        "business_clock": get_clock().now().isoformat(),
        "thread_id": target.thread["id"],
        "targets": {key: deepcopy(getattr(target, key)) for key in TARGET_FIELDS},
        "seeder": {
            key: sorted(value) if isinstance(value := getattr(target.seeder, key), set) else deepcopy(value)
            for key in SEEDER_FIELDS
        },
        "memory_observers": snapshot_memory(target),
        "tarot": {key: deepcopy(getattr(target.tarot, key)) for key in ("ids", "failed_reading", "retry_reading")},
        "runs": records,
        "metrics": {key: getattr(target.port, key) for key in ("calls", "external_calls")},
        **({"execution_budget": budgets} if budgets is not None else {}),
    }


def save_private(
    target: Any, session: str, binding: LifecycleBinding, turn: int, completed: dict | None = None
) -> tuple[str, str]:
    state = snapshot(target, binding, turn, completed)
    ident = "eval-lifecycle:" + session
    with target.repo.transaction(target.owner):
        old = target.repo.list(target.owner, "runtime_step", include_deleted=True)
        previous = next((row for row in old if row["id"] == ident), None)
        if previous and (previous["status"] != "active" or previous.get("stage") != STAGE):
            raise LifecycleError("私密生命周期记录不能恢复或覆盖")
        row = target.repo.put(
            target.owner,
            "runtime_step",
            ident,
            {
                "stage": STAGE,
                "run_id": target.run_ids[-1],
                "epoch": state["runs"][-1]["epoch"],
                "source_ids": [source["id"] for run in state["runs"] for source in run["sources"]],
                "state": state,
                "state_sha256": fingerprint(state),
            },
            subject=state["runs"][-1]["subject"],
            expected_revision=previous["revision"] if previous else 0,
            operation_id="eval-life:" + session + ":" + fingerprint(state),
        )
    return row["id"], row["state_sha256"]


def read_private(repo: PostgresRepository, owner: str, record: dict, binding: LifecycleBinding) -> dict[str, Any]:
    from .v4_execution_budget_store import verify_saved_budgets

    row = repo.get(owner, "runtime_step", record["state_id"], include_deleted=True)
    state = row.get("state")
    if (
        row["status"] != "active"
        or row.get("stage") != STAGE
        or not isinstance(state, dict)
        or fingerprint(state) != row.get("state_sha256")
        or row["state_sha256"] != record["state_sha256"]
        or state.get("format") != FORMAT
        or state.get("owner") != owner
        or state.get("model") != binding.model
    ):
        raise LifecycleError("私密生命周期状态已变化或失效")
    validate_seed(state["targets"]["seed"], binding)
    phase = state.get("phase", "primary_pending")
    if phase not in {"primary_pending", "primary_complete"}:
        raise LifecycleError("未知生命周期阶段")
    records = [
        run_identity(repo, owner, run["id"], current=phase == "primary_pending" and index == len(state["runs"]) - 1)
        for index, run in enumerate(state["runs"])
    ]
    if not records or records != state["runs"] or records[-1]["thread"] != state["thread_id"]:
        raise LifecycleError("原生运行、批次或来源与保存状态不符")
    if phase == "primary_complete":
        from .v4_completed_turn import verify_completed

        completed = state.get("completed_turn") or {}
        if completed.get("turn") != state["turn"] or completed.get("native", {}).get("run_id") != records[-1]["id"]:
            raise LifecycleError("完成观察不属于当前原生运行及轮次")
        verify_completed(repo, owner, state.get("completed_turn"))
    verify_saved_budgets(repo, owner, state, record, binding)
    return state


def restore(target: Any, state: dict[str, Any]) -> None:
    from mingjing_core.application.consultation import ConsultationService
    from tools.eval.targets.v4_scripted import ForbiddenLegacyModel

    for key, value in state["targets"].items():
        if key not in TARGET_FIELDS:
            raise LifecycleError("私密生命周期包含未知字段")
        setattr(target, key, deepcopy(value))
    target._ports()
    target.service = ConsultationService(target.repo, model=ForbiddenLegacyModel(), runtime=target.runtime)
    target.provider = ScriptedProvider(target.seed["_scripted"])
    target.seeder = V4PrivacySeeder(target.service, target.owner, target.seed["_scenario_id"])
    for key in SEEDER_FIELDS:
        value = state["seeder"][key]
        setattr(target.seeder, key, set(value) if key == "profile_fact_ids" else deepcopy(value))
    restore_memory(target, state)
    target.tarot = TarotDriver(target.service, target.seeder)
    for key, value in state["tarot"].items():
        setattr(target.tarot, key, deepcopy(value))
    clock = FrozenClock(datetime.fromisoformat(state["business_clock"]))
    target.thread = ThreadService(target.repo, clock=clock).get(target.owner, state["thread_id"])
    for key, value in state["metrics"].items():
        setattr(target.port, key, value)
    target.feishu = None
    target._budget_started = "execution_budget" in state
    target._budget_legacy = "execution_budget" not in state
