"""Actual committed answers and central Mock HTTP evidence, never fixture DB/event claims."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval import judge_journal, lifecycle_identity
from tools.eval.judge_journal import JudgeJournal
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_durable import DurableCore30Target

from .test_eval_v4_live_pg import Harness, wire
from .test_eval_v4_live_pg import live as live_fixture


@pytest.fixture
def live(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    yield from live_fixture.__wrapped__(p2_repo, monkeypatch)


@dataclass
class Completed:
    live: Harness
    target: DurableCore30Target
    control: LifecycleControl
    binding: LifecycleBinding

    def journal(self) -> JudgeJournal:
        return JudgeJournal(self.target, self.control, self.binding, self.live.guard)


@pytest.fixture
def completed(live: Harness, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lifecycle_identity, "candidate_provenance", lambda *args: {"worktree_clean": True})
    case = next(case for case in load_core30() if case.id == "T05")
    control = LifecycleControl(live.guard.store.dsn, "eval_control_" + uuid.uuid4().hex)
    control.initialize(live.guard)
    binding = LifecycleBinding.capture(live.guard, "a" * 40, case, "k3-256k")
    target = DurableCore30Target(
        model=binding.model, dsn=live.guard.store.dsn, environment=live.environment, adapter_factory=live.factory
    )
    live.targets.append(target)
    before = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(case.clock)))
    seed = case.seed.model_dump(mode="json")
    seed.update(
        _scenario_id=case.id,
        _clock=case.clock,
        _scripted=[step.model_dump(exclude_none=True) for step in case.scripted],
    )
    live.primary = lambda _: wire({"type": "text", "text": "合成已核对，结果已提交。"})
    try:
        # The helper's synthetic session has its own fixed allowlist.
        active = type(live.session)(live.guard, live.session.approval, phase="core", scenario_ids=["T05"])
        live.session = active
        with active.activate(), call_scope(active.scope("T05")):
            target.reset(seed)
            result = target.send({**case.turns[0].model_dump(mode="json", exclude={"expect"}), "_index": 1})
        target.checkpoint(control, binding, live.guard, turn=1, completed=result)
        yield Completed(live, target, control, binding)
    finally:
        set_clock(before)
        live.session.close()
        for item in live.targets:
            if item.repo is not None:
                item.repo.close()
                item.repo = None
        assert target.schema.startswith("eval_v4_") and control.schema.startswith("eval_control_")
        with psycopg.connect(live.guard.store.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(target.schema)))
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(control.schema)))


def test_completed_generation_and_score_survive_detach_without_execute_or_repost(
    completed: Completed, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = completed.journal()
    original_run = completed.target.repo.fetch_run(completed.target.owner, completed.target.run_ids[-1])
    prepared = journal.prepare()
    assert prepared["value"]["attempt_state"] == "prepared" and len(completed.live.sent) == 1
    judge = completed.live.judge()
    authorized = []
    with completed.live.session.activate(), judge.provider.tracker.authorize_before_send(lambda: authorized.append(1)):
        previous = judge.provider.tracker._before_send.get()
        score = journal.evaluate(judge)
        assert judge.provider.tracker._before_send.get() is previous
    assert authorized == [1] and judge.provider.tracker._before_send.get() is None
    assert score["score"] == 1 and score["error"] is None and len(completed.live.sent) == 2
    identity = (completed.target.schema, list(completed.target.run_ids), completed.target.thread["id"])
    session = completed.target.lifecycle_session
    completed.target.detach()

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("read-only result/score reuse must never execute a run or POST")

    monkeypatch.setattr(AgentRuntime, "execute", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    restored = DurableCore30Target(
        model=completed.binding.model,
        dsn=completed.target.dsn,
        environment=completed.live.environment,
        adapter_factory=completed.live.factory,
    )
    completed.live.targets.append(restored)
    restored.attach(completed.control, session, completed.binding, completed.live.guard)
    completed.target = restored
    observed = restored.completed_result(completed.control, completed.binding, completed.live.guard)
    assert observed.text == "合成已核对，结果已提交。" and observed.metadata["run_status"] == "succeeded"
    assert (restored.schema, restored.run_ids, restored.thread["id"]) == identity
    assert completed.journal().evaluate(completed.live.judge()) == score and len(completed.live.sent) == 2
    after = restored.repo.fetch_run(restored.owner, restored.run_ids[-1])
    assert (after["retry_epoch"], after["deadline_at"], after["usage"]) == (
        original_run["retry_epoch"],
        original_run["deadline_at"],
        original_run["usage"],
    )
    with pytest.raises(LifecycleError):
        restored.send({"_index": 1, "user": "must not run"})
    row = completed.journal().prepare()
    assert row["value"]["attempt_state"] == "completed" and len(row["value"]["attempt_ids"]) == 1
    public = json.dumps(completed.control.load(session, completed.binding, completed.live.guard), default=str)
    assert "合成已核对" not in public and '"payload"' not in public and '"seed"' not in public


def test_inflight_without_response_never_automatically_reposts(completed: Completed) -> None:
    journal = completed.journal()
    with completed.live.session.activate():
        row = journal._begin(completed.live.judge())
        assert row["value"]["attempt_state"] == "inflight"
        with pytest.raises(LifecycleError):
            journal.evaluate(completed.live.judge())
    assert len(completed.live.sent) == 1


def test_completed_checkpoint_refuses_fabricated_turn_result(completed: Completed) -> None:
    result = completed.target.completed_result(completed.control, completed.binding, completed.live.guard)
    result.text = "unproduced synthetic answer"
    with pytest.raises(LifecycleError):
        completed.target.checkpoint(
            completed.control, completed.binding, completed.live.guard, turn=1, completed=result
        )
    assert len(completed.live.sent) == 1


def test_incomplete_real_mock_response_is_unknown_and_cannot_repost(
    completed: Completed, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid(request: httpx.Request) -> httpx.Response:
        completed.live.sent.append(request)
        return wire(
            {
                "type": "tool_use",
                "id": "invalid-score",
                "name": "submit",
                "input": {"score": 2, "verdict": "pass", "issues": []},
            }
        )

    monkeypatch.setattr(completed.live, "handle", invalid)
    journal = completed.journal()
    with completed.live.session.activate(), pytest.raises(LifecycleError):
        journal.evaluate(completed.live.judge())
    sent = len(completed.live.sent)
    assert journal.prepare()["value"]["attempt_state"] == "unknown" and sent == 2
    with completed.live.session.activate(), pytest.raises(LifecycleError):
        journal.evaluate(completed.live.judge())
    assert len(completed.live.sent) == sent


@pytest.mark.parametrize("change", ["rubric", "schema", "source"])
def test_score_request_identity_changes_stop_before_post(
    completed: Completed, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    journal = completed.journal()
    journal.prepare()
    if change == "rubric":
        path = tmp_path / "synthetic-rubric.md"
        path.write_text("Changed synthetic rubric", encoding="utf-8")
        monkeypatch.setattr(judge_journal, "RUBRIC", path)
    elif change == "schema":
        monkeypatch.setattr(judge_journal, "JUDGE_SCHEMA", {"type": "null"})
    else:
        journal.binding = replace(completed.binding, source_sha256="c" * 64)
    with pytest.raises(LifecycleError):
        journal.evaluate(completed.live.judge())
    assert len(completed.live.sent) == 1


def test_native_source_withdrawal_erases_completed_result_and_score_private_bodies(completed: Completed) -> None:
    journal = completed.journal()
    with completed.live.session.activate():
        journal.evaluate(completed.live.judge())
    run = completed.target.repo.fetch_run(completed.target.owner, completed.target.run_ids[-1])
    source = completed.target.repo.get(completed.target.owner, "message", run["request"]["source_message_id"])
    SourceWithdrawalService(completed.target.service.memory).delete(
        completed.target.owner,
        run["subject"],
        source["id"],
        expected_revision=source["revision"],
        request_id="withdraw-completed-score",
    )
    with completed.target.repo.transaction(completed.target.owner) as connection:
        rows = connection.execute(
            sql.SQL("SELECT status,data FROM {} WHERE owner=%s AND kind='runtime_step' AND id=ANY(%s)").format(
                completed.target.repo.table("core_entities")
            ),
            (completed.target.owner, ["eval-lifecycle:" + completed.target.lifecycle_session, journal.ident]),
        ).fetchall()
    assert len(rows) == 2 and all(row["status"] == "deleted" and row["data"] == {} for row in rows)
    with pytest.raises((LifecycleError, CoreError)):
        journal.evaluate(completed.live.judge())
    assert len(completed.live.sent) == 2


def test_cached_score_rejects_changed_central_physical_evidence(completed: Completed) -> None:
    journal = completed.journal()
    with completed.live.session.activate():
        journal.evaluate(completed.live.judge())
    ident = journal.prepare()["value"]["attempt_ids"][0]
    with completed.live.guard.store.connect() as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET status='unknown' WHERE attempt_id=%s").format(
                completed.live.guard.store.table("core_model_usage")
            ),
            (ident,),
        )
    with pytest.raises(LifecycleError):
        journal.evaluate(completed.live.judge())
    assert len(completed.live.sent) == 2


def test_withdrawal_after_inflight_before_native_send_blocks_payload_and_clears_state(
    completed: Completed, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = completed.journal()
    judge = completed.live.judge()
    original = journal._begin

    def withdraw_after_begin(judge):
        row = original(judge)
        assert row["value"]["attempt_state"] == "inflight" and row["value"]["payload"]["answer"]
        run = completed.target.repo.fetch_run(completed.target.owner, completed.target.run_ids[-1])
        source = completed.target.repo.get(completed.target.owner, "message", run["request"]["source_message_id"])
        SourceWithdrawalService(completed.target.service.memory).delete(
            completed.target.owner,
            run["subject"],
            source["id"],
            expected_revision=source["revision"],
            request_id="withdraw-before-judge-send",
        )
        return row

    monkeypatch.setattr(journal, "_begin", withdraw_after_begin)
    with completed.live.session.activate(), pytest.raises(ProviderStopped):
        journal.evaluate(judge)
    assert len(completed.live.sent) == 1 and judge.provider.tracker.calls == 0
    assert judge.provider.tracker.external_calls == 0 and judge.provider.tracker._before_send.get() is None
    with completed.target.repo.transaction(completed.target.owner) as connection:
        rows = connection.execute(
            sql.SQL("SELECT status,data FROM {} WHERE owner=%s AND kind='runtime_step' AND id=ANY(%s)").format(
                completed.target.repo.table("core_entities")
            ),
            (completed.target.owner, ["eval-lifecycle:" + completed.target.lifecycle_session, journal.ident]),
        ).fetchall()
    assert len(rows) == 2 and all(row["status"] == "deleted" and row["data"] == {} for row in rows)
    with completed.live.session.activate(), pytest.raises((LifecycleError, CoreError)):
        journal.evaluate(judge)
    assert len(completed.live.sent) == 1
