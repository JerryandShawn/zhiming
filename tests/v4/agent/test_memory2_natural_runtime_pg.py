"""Historical replies/pending proposals are real; natural forgetting clears actual lineage."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from psycopg import sql

from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from mingjing_core.timekit.timestamps import history_instant
from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_memory_history_seed import declared_reply, pending_source_label
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as base_target


@pytest.fixture(name="target")
def natural_target(monkeypatch: pytest.MonkeyPatch) -> Iterator[V4Target]:
    yield from base_target.__wrapped__(monkeypatch)


def test_natural_forget_clears_actual_old_reply_and_pending_proposal(target: V4Target) -> None:
    original = next(c for c in load_scenarios(Path("tools/eval/scenarios")) if c.id == "F02")
    case = execution_overlay(original)
    assert scenario_contract_hash(case) == scenario_contract_hash(original)
    previous = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(case.clock)))
    seed = case.seed.model_dump(mode="json")
    seed.update(
        _scenario_id=case.id, _clock=case.clock, _scripted=[s.model_dump(exclude_none=True) for s in case.scripted]
    )
    try:
        target.reset(seed)
        proposal_id = target.memory_actions.ids["health-proposal"]
        reply_id = target.memory_actions.ids["anxiety-assistant"]
        before = target.repo.get(target.owner, "message", reply_id)
        assert before["run_id"] == target.run_ids[0] and not before.get("redacted")
        assert history_instant(before["at"]) == history_instant(seed["thread"][1]["at"])
        assert target.repo.get(target.owner, "proposal", proposal_id)["status"] == "pending"
        initial_fact = target.repo.get(target.owner, "fact", "anxiety")
        assert initial_fact["status"] == "active" and initial_fact["sensitivity"] == "health"
        source_id = target.seeder.ids["source-synthetic"]
        assert target.repo.get(target.owner, "proposal", proposal_id)["source_refs"][0]["message_id"] == source_id
        payload = case.turns[0].model_dump(mode="json", exclude={"expect"}, exclude_none=True)
        result = target.send({**payload, "_index": 1})
        assert result.error is None and "memory_forget" in result.tools_called
        assert target.repo.get(target.owner, "fact", "anxiety", include_deleted=True)["status"] == "deleted"
        assert target.repo.get(target.owner, "proposal", proposal_id, include_deleted=True)["status"] == "deleted"
        after = target.repo.get(target.owner, "message", reply_id)
        assert after["redacted"] and "焦虑症" not in after["content"]
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert run["status"] == "succeeded" and run["retry_epoch"] == 1
        with target.repo.transaction(target.owner) as connection:
            rows = connection.execute(
                sql.SQL("SELECT receipt FROM {} WHERE owner=%s AND operation='memory2_natural_forget'").format(
                    target.repo.table("core_mutation_requests")
                ),
                (target.owner,),
            ).fetchall()
        assert len(rows) == 1 and rows[0]["receipt"]["write_status"] == "deleted"
        assert rows[0]["receipt"]["id"] == "anxiety" and "content" not in rows[0]["receipt"]
        snapshot = target.repo.get(target.owner, "runtime_step", f"{run['id']}:e1:agent_initial_context")
        assert "anxiety" not in {v["id"] for v in snapshot["output"]["alias_map"].values()}
    finally:
        set_clock(previous)


def test_sensitive_pending_fixture_cannot_guess_among_sources() -> None:
    seed = {"facts": [{"source_message_id": ident, "sensitivity": "health"} for ident in ("one", "two")]}
    fixture = {"kind": "proposal", "data": {"sensitivity": "health"}}
    with pytest.raises(ValueError):
        pending_source_label(seed, fixture)


def test_declared_reply_keeps_source_chronology() -> None:
    seed = {
        "thread": [
            {"id": "u", "role": "user", "at": "2026-10-17T10:30:00+08:00"},
            {"id": "a", "role": "assistant", "at": "2026-10-16T10:30:00+08:00"},
        ]
    }
    with pytest.raises(ValueError):
        declared_reply(seed, "u")
