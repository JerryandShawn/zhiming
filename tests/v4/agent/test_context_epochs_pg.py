"""Real PG epoch reservations fence concurrent send metadata and current sources."""

from __future__ import annotations

import concurrent.futures
import json
from dataclasses import asdict, replace
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_types import ContextBuild, ContextInputError
from mingjing_core.agent.journal import Journal, JournalStep, input_fingerprint
from mingjing_core.application.context_epochs import ContextEpochService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict
from mingjing_core.models.port import ChatMessage
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive


def started(memory: MemoryService, source: dict[str, Any], context: ContextBuild, ident: str) -> JournalStep:
    repo = memory.repo
    run = repo.queue_run("alice", ident, {"source_message_id": source["id"]})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id='life:self' WHERE owner='alice' AND id=%s").format(
                repo.table("core_runs")
            ),
            (run["id"],),
        )
    run = repo.claim_run("alice", run["id"])
    identity = {
        "messages": [asdict(row) for row in context.budget.messages],
        "tools": [asdict(row) for row in context.budget.tools],
        "tool_choice": "auto",
        "source_versions": context.injected_versions,
    }
    return Journal(repo, "alice").next_or_replay(run, kind="model", input_fp=input_fingerprint("model", "", identity))


def test_two_turns_append_bytes_and_reopen_keeps_metadata_only(memory: MemoryService) -> None:
    engine, repo = ContextEngine(memory, "合成系统"), memory.repo
    first_source = receive(memory, "第一轮合成正文", "first")
    first = engine.build("alice", first_source["id"])
    service = ContextEpochService(repo)
    step = started(memory, first_source, first, "first-send")
    before = repo.get_revision("alice")
    receipt = service.mark_sent(step, first)
    assert service.mark_sent(step, first) == receipt and repo.get_revision("alice") == before + 1
    memory.record_assistant_message("alice", "self", "life:self", "合成回答", run_id=step.run_id, channel="web")
    get_clock().advance(timedelta(minutes=1))
    second_source = receive(memory, "第二轮合成正文", "second")
    second = engine.build("alice", second_source["id"])
    second_step = started(memory, second_source, second, "second-send")
    assert service.mark_sent(second_step, second)["compression_epoch"] == receipt["compression_epoch"]
    reopened = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        cache = reopened.get("alice", "thread", "life:self")["context_cache"]
        assert cache["generation"] == 2 and len(cache["l5_hashes"]) == 2
        assert "合成" not in json.dumps(cache, ensure_ascii=False)
    finally:
        reopened.close()


def test_withdrawal_rebuild_starts_new_epoch_and_old_snapshot_cannot_send(memory: MemoryService) -> None:
    engine, service = ContextEngine(memory, "合成系统"), ContextEpochService(memory.repo)
    old = receive(memory, "我不能上夜班。其余合成信息", "old")
    fact = memory.save_fact("alice", "self", old["id"], "我不能上夜班", "constraint")
    current = receive(memory, "合成当前问题")
    first = engine.build("alice", current["id"])
    step = started(memory, current, first, "before-withdrawal")
    service.mark_sent(step, first)
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    with pytest.raises((RevisionConflict, EvidenceError)):
        service.mark_sent(step, first)
    clean = engine.build("alice", current["id"])
    assert clean.cache_epoch.epoch == first.cache_epoch.epoch + 1
    assert clean.cache_epoch.reset_reason == "sources_changed"
    assert "我不能上夜班" not in "\n".join(row.content for row in clean.messages)
    clean_step = started(memory, current, clean, "after-withdrawal")
    assert service.mark_sent(clean_step, clean)["reset_reason"] == "sources_changed"


def test_two_concurrent_reservations_from_same_generation_only_one_commits(memory: MemoryService) -> None:
    source = receive(memory, "合成并发问题")
    context = ContextEngine(memory, "合成系统").build("alice", source["id"])
    steps = [started(memory, source, context, "concurrent-" + str(index)) for index in range(2)]

    def send(step: JournalStep) -> str:
        try:
            ContextEpochService(memory.repo).mark_sent(step, context)
            return "committed"
        except RevisionConflict:
            return "stale"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(send, steps)) == ["committed", "stale"]
    assert memory.repo.get("alice", "thread", "life:self")["context_cache"]["generation"] == 1


def test_expired_lease_changed_request_and_changed_budget_cannot_mark_sent(memory: MemoryService) -> None:
    source = receive(memory, "合成当前问题")
    context = ContextEngine(memory, "合成系统").build("alice", source["id"])
    step = started(memory, source, context, "safe-input")
    service = ContextEpochService(memory.repo)
    with pytest.raises(EvidenceError):
        service.mark_sent(replace(step, input_fp="0" * 64), context)
    layer = context.budget.layers[0]
    changed = replace(layer, items=(replace(layer.items[0], messages=(ChatMessage("system", "改写系统"),)),))
    forged_budget = replace(context.budget, layers=(changed, *context.budget.layers[1:]))
    with pytest.raises(ContextInputError):
        service.mark_sent(step, context, budget=forged_budget)
    with memory.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s").format(
                memory.repo.table("core_runs")
            ),
            (step.run_id,),
        )
    with pytest.raises(LeaseConflict):
        service.mark_sent(step, context)
    assert not memory.repo.list("alice", "thread")


def test_window_compression_changes_epoch_but_next_appends_do_not(memory: MemoryService) -> None:
    engine, service, epochs = ContextEngine(memory, "合成系统"), ContextEpochService(memory.repo), {}
    for index in range(1, 52):
        source = receive(memory, f"合成轮次{index}", str(index))
        if index in {40, 41, 50, 51}:
            context = engine.build("alice", source["id"])
            step = started(memory, source, context, "window-" + str(index))
            epochs[index] = service.mark_sent(step, context)["compression_epoch"]
        get_clock().advance(timedelta(minutes=1))
    assert epochs == {40: 0, 41: 1, 50: 1, 51: 2}
