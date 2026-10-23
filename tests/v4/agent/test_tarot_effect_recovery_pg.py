"""One real fixed deck survives a committed tarot effect without Journal ack."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_agent_runtime_pg import invoke
from .test_loop_cycle_support import ScriptedPort, answer, modify
from .test_loop_cycle_support import cycle_repo as source_fixture
from .tool_effect_recovery_support import mutation_row, operation_rows, queued, step_row

QUESTION = "请用塔罗看这次合成面试要注意什么"


@pytest.fixture
def tarot_effect_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def native_state(repo: PostgresRepository) -> dict[str, list[dict[str, Any]]]:
    with repo.transaction() as connection:
        return {
            table: connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner='alice' ORDER BY {}").format(
                    repo.table(table), sql.SQL("id" if table != "tarot_requests" else "operation,request_key")
                )
            ).fetchall()
            for table in ("tarot_draws", "tarot_requests", "tarot_readings")
        }


class TarotCrash:
    def __init__(self, repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count, self.shuffles, self.step, self.output = 0, 0, None, None
        original, shuffle = Journal.complete, TarotService._shuffle

        def shuffled(service: TarotService, reversals: bool) -> list[dict[str, Any]]:
            self.shuffles += 1
            return shuffle(service, reversals)

        def interrupt(journal: Journal, step: JournalStep, output: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            if step.kind == "tool" and step.name == "tarot_start" and self.count == 0:
                receipt = output["receipt"]
                assert receipt["write_status"] == "saved" and receipt["kind"] == "draw"
                with repo.pool.connection() as connection:
                    mutation = connection.execute(
                        sql.SQL(
                            "SELECT receipt FROM {} WHERE owner=%s AND operation='agent_tarot_start' AND request_key=%s"
                        ).format(repo.table("core_mutation_requests")),
                        (step.owner, step.operation_id),
                    ).fetchone()
                    draw = connection.execute(
                        sql.SQL("SELECT id FROM {} WHERE owner=%s AND id=%s").format(repo.table("tarot_draws")),
                        (step.owner, receipt["draw_id"]),
                    ).fetchone()
                    request = connection.execute(
                        sql.SQL(
                            "SELECT result_id FROM {} WHERE owner=%s AND operation='create' AND request_key=%s"
                        ).format(repo.table("tarot_requests")),
                        (step.owner, step.operation_id),
                    ).fetchone()
                assert mutation and mutation["receipt"] == receipt
                assert draw and request and draw["id"] == request["result_id"] == receipt["draw_id"]
                self.count, self.step, self.output = 1, step, copy.deepcopy(output)
                raise SystemExit("synthetic-tarot-effect-before-ack")
            return original(journal, step, output, *args, **kwargs)

        monkeypatch.setattr(TarotService, "_shuffle", shuffled)
        monkeypatch.setattr(Journal, "complete", interrupt)


def crashed(
    repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, mode: str = "pick"
) -> tuple[dict[str, Any], TarotCrash, ScriptedPort]:
    run, crash = queued(repo, QUESTION, []), TarotCrash(repo, monkeypatch)
    args = {"question": QUESTION, "message_id": run["request"]["source_message_id"], "draw_source": mode}
    first = ScriptedPort([answer("", [ToolCall("draw", "tarot_start", args)])])
    with pytest.raises(SystemExit, match="synthetic-tarot-effect-before-ack"):
        invoke(repo, run, first)
    assert crash.step is not None and crash.output is not None and crash.count == crash.shuffles == 1
    step = step_row(repo, crash.step)
    assert (
        step["status"] == "started" and step["output"] is None and step["finished_at"] is None and step["usage"] == {}
    )
    return run, crash, first


@pytest.mark.parametrize("mode", ["auto", "pick"])
def test_tarot_started_effect_reclaims_same_epoch_with_one_fixed_deck(
    tarot_effect_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    repo = tarot_effect_repo
    run, crash, first = crashed(repo, monkeypatch, mode)
    before = native_state(repo)
    mutation, operations, cases = (
        mutation_row(repo, crash.step),
        operation_rows(repo, crash.step),
        repo.list("alice", "case"),
    )
    draw = before["tarot_draws"][0]
    assert len(before["tarot_draws"]) == len(before["tarot_requests"]) == len(repo.list("alice", "case")) == 1
    assert len(draw["private_deck"]) == len({card["card_id"] for card in draw["private_deck"]}) == 78
    assert len({card["back_id"] for card in draw["private_deck"]}) == 78
    assert len(draw["payload"]["selected"]) == (3 if mode == "auto" else 0)
    assert "private_deck" not in str(crash.output) and all(
        "card_id" not in card for card in crash.output["data"]["draw"]["cards"]
    )
    source = repo.get("alice", "message", run["request"]["source_message_id"])
    modify(repo, run, "lease_until=now()-interval '1 second'")
    resumed = repo.claim_run("alice", run["id"], lease_seconds=150)
    assert resumed["retry_epoch"] == run["retry_epoch"] and resumed["lease_token"] != run["lease_token"]
    port = ScriptedPort([answer("固定牌阵已保留，等待你选牌或揭牌。")])
    result, events = invoke(repo, resumed, port)
    assert result["text"] == "固定牌阵已保留，等待你选牌或揭牌。"
    assert native_state(repo) == before and crash.count == crash.shuffles == 1
    assert mutation_row(repo, crash.step) == mutation and operation_rows(repo, crash.step) == operations
    assert step_row(repo, crash.step)["output"] == crash.output and step_row(repo, crash.step)["status"] == "completed"
    assert result["usage"]["replayed_model_steps"] == 1 and len(first.requests) == len(port.requests) == 1
    assert repo.get("alice", "message", source["id"]) == source
    assert repo.list("alice", "case") == cases and sum(event["type"] == "final" for event in events) == 1


@pytest.mark.parametrize("action", ["run_cancel", "draw_cancel", "source_message", "source_span"])
def test_tarot_cancel_or_withdrawal_never_recovers_a_committed_unacknowledged_draw(
    tarot_effect_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    repo = tarot_effect_repo
    run, crash, _ = crashed(repo, monkeypatch)
    draw_id = crash.output["receipt"]["draw_id"]
    if action == "run_cancel":
        DispatcherCancellation(repo).request("alice", run["id"])
    elif action == "draw_cancel":
        TarotService(repo).cancel("alice", draw_id)
    elif action == "source_message":
        source = repo.get("alice", "message", run["request"]["source_message_id"])
        repo.delete("alice", "message", source["id"], expected_revision=source["revision"])
    else:
        with repo.transaction("alice") as connection:
            repo.revoke(
                connection,
                "alice",
                "source_span",
                "synthetic-draw-range",
                "stopped",
                {"message_id": run["request"]["source_message_id"], "start": 0, "end": 1},
            )
    before = native_state(repo)
    port = ScriptedPort([])
    with pytest.raises(CoreError):
        invoke(repo, run, port)
    assert native_state(repo) == before and port.requests == [] and crash.shuffles == crash.count == 1
    assert repo.fetch_run("alice", run["id"])["result"] is None
    assert step_row(repo, crash.step)["status"] == "started"
    assert not [message for message in repo.list("alice", "message") if message.get("role") == "assistant"]
