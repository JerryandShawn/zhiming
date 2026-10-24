"""Native step/permit UUID anchors with real PG; only model transport is replaced."""

from __future__ import annotations

import json
from dataclasses import asdict

import httpx
import pytest
from models.test_quota_http_pg import rows
from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.application import agent_model_attempts as attempts
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.context_usage import ContextUsageService
from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.models.quota_attempt_observer import (
    ModelAttemptUnconfirmed,
    current_observer,
    defer_send_counter,
)
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.lifecycle_identity import LifecycleBinding
from tools.eval.quota import ProviderStopped

from .model_attempt_support import Observed, finish_before_publication, native_step
from .model_attempt_support import observed as shared_observed
from .test_eval_lifecycle_pg import seed
from .test_eval_v4_live_pg import wire


@pytest.fixture(name="observed")
def observed_fixture(p2_repo, monkeypatch, request):
    yield from shared_observed.__wrapped__(p2_repo, monkeypatch, request)


def test_default_live_path_has_no_dispatch_and_core_rejects_untrusted_guard(observed: Observed):
    target = observed.live.target()
    target.reset(seed(observed.case))
    target.send({**observed.case.turns[0].model_dump(mode="json", exclude={"expect"}), "_index": 1})
    assert not [
        row for row in target.repo.list(target.owner, "runtime_step") if row.get("stage") == "agent_model_attempts"
    ]
    binding = LifecycleBinding.capture(observed.live.guard, "a" * 40, observed.case, "k3-256k")
    other = QuotaGuard(
        central_dsn=observed.live.guard.store.dsn,
        central_schema=observed.live.guard.store.schema,
        account_id=observed.live.guard.store.account_id,
        ledger_identity=observed.live.guard.store.identity,
    )
    with (
        pytest.raises(ModelAttemptUnconfirmed),
        attempts.core_observation(target.repo, target.owner, other, asdict(binding), lambda: binding.verify(other)),
    ):
        pytest.fail("another guard instance cannot enable observation")
    assert len(observed.live.sent) == 1 and current_observer() is None


@pytest.mark.parametrize("observed", ["M01"], indirect=True)
def test_actual_tool_primary_critic_revision_have_exact_native_step_uuids(observed: Observed):
    target, live = observed.target, observed.live
    registry = target.port.port.registry
    target.runtime.reviewer.port = registry.port("critic", factory=live.factory, stop_on_quota=True)
    count = 0

    def respond(request):
        nonlocal count
        count += 1
        if count == 1:
            return wire(
                {
                    "type": "tool_use",
                    "id": "anchor-write",
                    "name": "memory_write",
                    "input": {
                        "message_id": target.bindings["turn-1"],
                        "quote": "我下周三有个面试",
                        "summary": "合成锚点面试",
                        "kind": "event",
                        "date_expression": "下周三",
                    },
                }
            )
        text = (
            "初稿合成结论"
            if count == 2
            else json.dumps(
                {
                    "verdict": "revise",
                    "issues": [{"type": "fatalism", "quote": "初稿", "severity": 4, "fix_hint": "改写"}],
                }
            )
            if count == 3
            else "合成修订结论"
        )
        return wire({"type": "text", "text": text})

    live.primary = respond
    result = observed.send()
    links, usage = observed.links(), rows(live.guard)
    assert not result.error and result.text == "合成修订结论" and len(live.sent) == 4
    assert [
        (row["value"]["role"], row["value"]["name"]) for row in sorted(links, key=lambda row: row["value"]["seq"])
    ] == [("primary", ""), ("primary", ""), ("critic", "critic"), ("primary", "revision")]
    assert {entry["attempt_id"] for row in links for entry in row["value"]["attempts"]} == {
        row["attempt_id"] for row in usage
    }
    assert all(
        entry["state"] == "finished" and entry["result_kind"] == "ok"
        for row in links
        for entry in row["value"]["attempts"]
    )
    assert sum(row.get("summary") == "合成锚点面试" for row in target.repo.list(target.owner, "fact")) == 1
    assert current_observer() is None


@pytest.mark.parametrize("stage", ["logical_intent", ":intent", ":admitted"])
def test_failed_private_save_never_posts(observed: Observed, monkeypatch: pytest.MonkeyPatch, stage: str):
    original = PostgresRepository.put

    def reject(self, owner, kind, ident, data, **kwargs):
        if data.get("stage") == "agent_model_attempts" and kwargs.get("operation_id", "").endswith(stage):
            raise RevisionConflict("SYNTHETIC_PRIVATE_PUT_FAILURE")
        return original(self, owner, kind, ident, data, **kwargs)

    monkeypatch.setattr(PostgresRepository, "put", reject)
    with pytest.raises(ProviderStopped):
        observed.send()
    assert not observed.live.sent and observed.target.port.calls == observed.target.port.external_calls == 0
    usage = rows(observed.live.guard)
    assert len(usage) == int(stage == ":admitted") and observed.live.guard.status()["in_flight"] == 0


@pytest.mark.parametrize("field", ["run_id", "model", "scenario_id"])
def test_actual_admitted_identity_mismatch_stops_before_http(
    observed: Observed, monkeypatch: pytest.MonkeyPatch, field: str
):
    original = attempts.StepAttempts.prepare

    def mismatch(self, guard, scope, ident, role, provider, model):
        if field == "model":
            model = "k3"
        else:
            from dataclasses import replace

            scope = replace(scope, **{field: "synthetic-mismatch"})
        return original(self, guard, scope, ident, role, provider, model)

    monkeypatch.setattr(attempts.StepAttempts, "prepare", mismatch)
    with pytest.raises(ProviderStopped):
        observed.send()
    assert not observed.live.sent and not rows(observed.live.guard)


def test_completed_journal_only_validates_without_permit_or_new_intent(
    observed: Observed, monkeypatch: pytest.MonkeyPatch
):
    step = finish_before_publication(observed, monkeypatch)
    count, links = len(rows(observed.live.guard)), observed.links()
    monkeypatch.setattr(QuotaGuard, "acquire", lambda *args, **kwargs: pytest.fail("completed read must not acquire"))
    with observed.scope():
        observed.target.runtime.ledger.completed(step)
    assert len(observed.live.sent) == count == 1 and observed.links() == links


def test_http_success_without_journal_commit_refuses_second_dispatch(
    observed: Observed, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        Journal, "complete", lambda *args, **kwargs: (_ for _ in ()).throw(EvidenceError("SYNTHETIC_JOURNAL_FAILURE"))
    )
    with pytest.raises(ProviderStopped):
        observed.send()
    step = native_step(observed)
    assert not step.completed and rows(observed.live.guard)[0]["status"] == "ok"
    with observed.scope(), pytest.raises(ModelAttemptUnconfirmed), observed.target.runtime.ledger.physical(step):
        pytest.fail("existing dispatch must never be entered again")
    assert len(observed.live.sent) == len(rows(observed.live.guard)) == 1


@pytest.mark.parametrize("damage", ["missing", "unfinished", "changed", "journal"])
def test_exact_uuid_missing_unknown_or_tampered_cannot_replay(
    observed: Observed, monkeypatch: pytest.MonkeyPatch, damage: str
):
    step = finish_before_publication(observed, monkeypatch)
    usage = rows(observed.live.guard)[0]
    with observed.live.guard.store.connect() as connection:
        table = observed.live.guard.store.table("core_model_usage")
        if damage == "journal":
            connection.execute(
                sql.SQL("UPDATE {} SET status='started' WHERE run_id=%s AND seq=%s").format(
                    observed.target.repo.table("core_run_steps")
                ),
                (step.run_id, step.seq),
            )
        elif damage == "missing":
            connection.execute(sql.SQL("DELETE FROM {} WHERE attempt_id=%s").format(table), (usage["attempt_id"],))
        elif damage == "unfinished":
            connection.execute(
                sql.SQL("UPDATE {} SET status='reserved',finished_at=NULL WHERE attempt_id=%s").format(table),
                (usage["attempt_id"],),
            )
        else:
            connection.execute(
                sql.SQL("UPDATE {} SET output_tokens=999 WHERE attempt_id=%s").format(table), (usage["attempt_id"],)
            )
    with observed.scope(), pytest.raises(ModelAttemptUnconfirmed):
        observed.target.runtime.ledger.completed(step)
    assert len(observed.live.sent) == 1


@pytest.mark.parametrize("failure", ["none", "quota", "finish"])
def test_finished_observer_reads_only_after_guard_finish_and_keeps_stop_priority(
    observed: Observed, monkeypatch: pytest.MonkeyPatch, failure: str
):
    original = attempts.StepAttempts.finished
    checked = []

    def after(self, guard, scope, ident):
        record = next(row for row in rows(guard) if row["attempt_id"] == ident)
        checked.append(record["finished_at"])
        return original(self, guard, scope, ident)

    monkeypatch.setattr(attempts.StepAttempts, "finished", after)
    if failure == "quota":
        observed.live.primary = lambda _: httpx.Response(
            403,
            headers={"Retry-After": "18000"},
            json={"error": {"type": "permission_error", "message": "5-hour usage limit"}},
        )
    if failure == "finish":
        monkeypatch.setattr(
            observed.live.guard.store,
            "finalizing",
            lambda connection, now: connection.execute("SELECT synthetic_finish_failure()"),
        )
    if failure == "none":
        assert not observed.send().error
    else:
        with pytest.raises(ProviderStopped) as caught:
            observed.send()
        assert caught.value.reason == ("quota_5h" if failure == "quota" else "ledger_unavailable")
        if failure == "quota":
            assert caught.value.resume_at is not None
    assert len(checked) == 1 and (checked[0] is None) is (failure == "finish") and len(observed.live.sent) == 1


@pytest.mark.parametrize("mode", ["withdraw", "counter", "revision", "central"])
def test_final_send_recheck_erases_private_links_or_stops_counter_failure(
    observed: Observed, monkeypatch: pytest.MonkeyPatch, mode: str
):
    target = observed.target
    if mode == "withdraw":

        def revoke():
            run = target.repo.fetch_run(target.owner, target.run_ids[-1])
            source = target.repo.get(target.owner, "message", run["request"]["source_message_id"])
            SourceWithdrawalService(target.service.memory).delete(
                target.owner,
                run["subject"],
                source["id"],
                expected_revision=source["revision"],
                request_id="before-send-withdrawal",
            )

        context = target.port.authorize_before_send(revoke)
    elif mode in {"revision", "central"}:

        def change_admission():
            if mode == "revision":
                row = observed.links()[-1]
                target.repo.update(
                    target.owner,
                    "runtime_step",
                    row["id"],
                    {"value": row["value"]},
                    expected_revision=row["revision"],
                    operation_id="change-admitted-revision",
                )
            else:
                entry = rows(observed.live.guard)[-1]
                with observed.live.guard.store.connect() as connection:
                    connection.execute(
                        sql.SQL("UPDATE {} SET status='ok',finished_at=now() WHERE attempt_id=%s").format(
                            observed.live.guard.store.table("core_model_usage")
                        ),
                        (entry["attempt_id"],),
                    )

        context = target.port.authorize_before_send(change_admission)
    else:
        monkeypatch.setattr(target.port, "_count_request", lambda: (_ for _ in ()).throw(ModelAttemptUnconfirmed()))
        context = target.port.authorize_before_send(lambda: None)
    with context, pytest.raises(ProviderStopped):
        observed.send()
    assert not observed.live.sent and target.port.calls == target.port.external_calls == 0
    assert observed.adapters and all(adapter.request_count == 0 for adapter in observed.adapters)
    if mode == "withdraw":
        with target.repo.transaction(target.owner) as connection:
            private = connection.execute(
                sql.SQL("SELECT status,data FROM {} WHERE owner=%s AND kind='runtime_step'").format(
                    target.repo.table("core_entities")
                ),
                (target.owner,),
            ).fetchall()
        assert private and all(row["status"] == "deleted" and row["data"] == {} for row in private)
    assert current_observer() is None and not defer_send_counter(lambda: pytest.fail("not observed"))


@pytest.mark.parametrize("fault", ["reserve", "usage", "journal", "critic_usage", "critic_journal", "process"])
def test_raw_persistence_failures_and_process_control_are_not_outcomes_or_skips(
    observed: Observed, monkeypatch: pytest.MonkeyPatch, fault: str
):
    target, live = observed.target, observed.live
    if fault.startswith("critic"):
        target.runtime.reviewer.port = target.port.port.registry.port(
            "critic", factory=live.factory, stop_on_quota=True
        )
        live.primary = lambda _: wire(
            {"type": "text", "text": "合成初稿" if len(live.sent) == 1 else '{"verdict":"pass","issues":[]}'}
        )
    cls, method = (
        (RequestLedger, "reserve")
        if fault == "reserve"
        else (ContextUsageService, "record")
        if "usage" in fault
        else (Journal, "complete")
    )
    original = getattr(cls, method)

    def reject(self, step, *args, **kwargs):
        if not fault.startswith("critic") or step.name == "critic":
            raise RevisionConflict("SYNTHETIC_NATIVE_PERSISTENCE_FAILURE")
        return original(self, step, *args, **kwargs)

    if fault == "process":
        monkeypatch.setattr(target.runtime, "execute", lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit()))
    else:
        monkeypatch.setattr(cls, method, reject)
    with pytest.raises(SystemExit if fault == "process" else ProviderStopped):
        observed.send()
    expected = 0 if fault in {"reserve", "process"} else 2 if fault.startswith("critic") else 1
    assert len(live.sent) == len(rows(live.guard)) == expected
    assert target.repo.fetch_run(target.owner, target.run_ids[-1])["status"] != "succeeded"
