"""Persist memory evaluator observations without reseeding business state on attach."""

from copy import deepcopy
from typing import Any

from tools.eval.lifecycle_identity import LifecycleError

from .v4_memory_actions import MemoryActionDriver
from .v4_memory_privacy_seed import MemoryPrivacySeeder
from .v4_memory_withdraw_driver import MemoryWithdrawDriver

PRIVACY_FIELDS = (
    "ids",
    "source_ids",
    "embedding_targets",
    "runtime_ids",
    "setup_calls",
    "query_tokens",
    "query_ids",
    "baseline",
)


def snapshot_memory(target: Any) -> dict:
    privacy = target.privacy_seed
    values = {}
    for key in PRIVACY_FIELDS:
        value = getattr(privacy, key)
        values[key] = sorted(value) if isinstance(value, set) else deepcopy(value)
    return {
        "judge_action_history": deepcopy(getattr(target, "judge_action_history", [])),
        "privacy": values,
        "actions": {key: deepcopy(getattr(target.memory_actions, key)) for key in ("ids", "revisions", "setup_calls")},
        "withdrawals": [[list(key), value] for key, value in target.memory_withdrawals.original_revisions.items()],
    }


def restore_memory(target: Any, state: dict) -> None:
    # Constructors only create observers. Calling seed() here would replay writes.
    target.privacy_seed = MemoryPrivacySeeder(target)
    target.memory_actions = MemoryActionDriver(target)
    target.memory_withdrawals = MemoryWithdrawDriver(target)
    saved = state.get("memory_observers")
    if saved is None:
        if target.seeder.privacy_layers or any(
            item["kind"]
            in {
                "profile_item",
                "run_step",
                "run_event",
                "search_hit",
                "embedding",
                "proposal",
            }
            for item in target.seed.get("entities", [])
        ):
            raise LifecycleError("旧断点缺少记忆观察证据，不能重建过去的基线")
        return
    target.judge_action_history = deepcopy(saved.get("judge_action_history", []))
    for key in PRIVACY_FIELDS:
        value = deepcopy(saved["privacy"][key])
        if key in {"source_ids", "query_ids"}:
            value = set(value)
        elif key == "embedding_targets":
            value = {tuple(item) for item in value}
        elif key == "query_tokens":
            value = tuple(value)
        setattr(target.privacy_seed, key, value)
    for key in ("ids", "revisions", "setup_calls"):
        setattr(target.memory_actions, key, deepcopy(saved["actions"][key]))
    target.memory_withdrawals.original_revisions = {tuple(key): value for key, value in saved["withdrawals"]}
