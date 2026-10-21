"""Already-sent L5 fragments may append; rewrites require a new explicit epoch."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from mingjing_core.agent.context_budget import apply_budget
from mingjing_core.agent.context_epochs import epoch_plan, layer_bytes
from mingjing_core.agent.context_types import ContextInputError, ContextItem, ContextLayer
from mingjing_core.models.port import ChatMessage


def budget(*history: str):
    stable = [
        ContextLayer(name, (ContextItem(name, (ChatMessage("system", name),), True),))
        for name in ("L0", "L2", "L3_STABLE")
    ]
    rows = tuple(ContextItem(str(index), (ChatMessage("user", text),)) for index, text in enumerate(history))
    return apply_budget(
        (
            *stable,
            ContextLayer("L5", rows),
            ContextLayer("L1", (ContextItem("now", (ChatMessage("system", "现在"),), True),)),
        )
    )


def saved(plan) -> dict:
    value = asdict(plan)
    value["generation"] = value.pop("base_generation") + 1
    return value


def test_append_keeps_exact_sent_bytes_and_epoch() -> None:
    first, second = budget("第一轮🙂"), budget("第一轮🙂", "第二轮 é")
    plan = epoch_plan(first, {}, 1, {}, invalidated=False)
    appended = epoch_plan(second, {}, 2, saved(plan), invalidated=False)
    assert appended.epoch == plan.epoch and appended.l5_hashes[:1] == plan.l5_hashes
    assert layer_bytes(second, {"L5"}).startswith(layer_bytes(first, {"L5"}))


@pytest.mark.parametrize("text", ["删短", "改写了第一轮", ""])
def test_unexplained_rewrite_never_reuses_epoch(text: str) -> None:
    plan = epoch_plan(budget("原已发第一轮", "原已发第二轮"), {}, 1, {}, invalidated=False)
    with pytest.raises(ContextInputError) as caught:
        epoch_plan(budget(text), {}, 2, saved(plan), invalidated=False)
    assert caught.value.code == "context_l5_append_only_violation"


@pytest.mark.parametrize("reason", ["compression", "sources_changed"])
def test_only_explicit_compression_or_invalidated_sources_rewrite_l5(reason: str) -> None:
    old = epoch_plan(budget("原第一轮", "原第二轮"), {"message:old": 1}, 1, {}, invalidated=False)
    current = budget("洁净新窗口")
    if reason == "compression":
        current = replace(current, compression_trace=({"action": "L5_drop", "before": 130_000, "after": 20_000},))
    result = epoch_plan(current, {}, 2, saved(old), invalidated=reason == "sources_changed")
    assert result.epoch == old.epoch + 1 and result.reset_reason == reason


def test_volatile_now_and_retrieval_do_not_change_stable_cache_prefix() -> None:
    original = budget("已发历史")
    plan = epoch_plan(original, {}, 1, {}, invalidated=False)
    now = ContextLayer("L1", (ContextItem("now", (ChatMessage("system", "另一时刻"),), True),))
    lookup = ContextLayer("L4", (ContextItem("hit", (ChatMessage("system", "另一条检索"),)),))
    changed = replace(original, layers=(*original.layers[:-1], lookup, now))
    after = epoch_plan(changed, {}, 2, saved(plan), invalidated=False)
    assert after.prefix_sha256 == plan.prefix_sha256 and after.epoch == plan.epoch


def test_rebuilding_identical_compressed_history_does_not_churn_epoch() -> None:
    current = replace(
        budget("已压缩后保留的内容"), compression_trace=({"action": "L5_drop", "before": 130_000, "after": 20_000},)
    )
    first = epoch_plan(current, {}, 1, {}, invalidated=False)
    second = epoch_plan(current, {}, 2, saved(first), invalidated=False)
    assert second.epoch == first.epoch and second.reset_reason is None
