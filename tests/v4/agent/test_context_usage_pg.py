"""D2 alerts survive repository reopening without storing conversation text."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.context_types import MeterResult
from mingjing_core.agent.journal import Journal, input_fingerprint
from mingjing_core.application.context_usage import ContextUsageService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository


def run(repo: PostgresRepository, ident: str) -> dict[str, Any]:
    row = repo.queue_run("alice", ident, {"message": "合成用量请求"})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id='life:self' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            ("alice", row["id"]),
        )
    return repo.claim_run("alice", row["id"])


def completed(repo: PostgresRepository, ident: str, usage: dict[str, Any]):
    row = run(repo, ident)
    journal = Journal(repo, "alice")
    step = journal.next_or_replay(row, kind="model", input_fp=input_fingerprint("model", "", {}))
    return journal.complete(step, {"text": "合成回答"}, usage)


def meter(upper: int | None = 70_000) -> MeterResult:
    return replace(
        MeterResult(100, 100),
        input_token_upper_bound=upper,
        estimated_input_tokens=65_000,
        token_meter_version="synthetic",
    )


def test_third_large_actual_alert_persists_and_replay_does_not_increment(
    p2_repo: PostgresRepository,
) -> None:
    for index in range(3):
        step = completed(p2_repo, str(index), {"input_tokens": 70_000})
        service = ContextUsageService(p2_repo)
        receipt = service.record(step, meter())
        assert receipt["actual_streak"] == index + 1
        assert receipt["actual_alert"] is (index == 2)
        assert service.record(step, meter()) == receipt
        assert Journal(p2_repo, "alice").complete(step, {"text": "合成回答"}, {"input_tokens": 70_000}).usage == {
            "input_tokens": 70_000
        }
    reopened = PostgresRepository(p2_repo.dsn, schema=p2_repo.schema, initialize=False)
    try:
        row = ContextUsageService(reopened).record(completed(reopened, "fourth", {"input_tokens": 70_001}), meter())
        assert row["actual_streak"] == 4 and not row["actual_alert"]
        reset = ContextUsageService(reopened).record(completed(reopened, "reset", {"input_tokens": 60_000}), meter())
        assert reset["actual_streak"] == 0 and reset["measured_upper_streak"] == 5
    finally:
        reopened.close()


def test_unknown_actual_is_null_and_only_measured_alert_is_emitted(
    p2_repo: PostgresRepository,
) -> None:
    for index in range(3):
        receipt = ContextUsageService(p2_repo).record(completed(p2_repo, str(index), {}), meter())
    assert receipt["actual_input_tokens"] is None and receipt["actual_streak"] == 0
    assert receipt["measured_upper_alert"] and not receipt["actual_alert"]
    state = p2_repo.get("alice", "thread", "life:self")["context_guard"]
    assert "合成" not in str(state)


@pytest.mark.parametrize("invalid", [True, -1, 1.5, "70000"])
def test_invalid_provider_usage_cannot_be_counted(p2_repo: PostgresRepository, invalid: object) -> None:
    step = completed(p2_repo, "invalid", {"input_tokens": invalid})
    with pytest.raises(EvidenceError):
        ContextUsageService(p2_repo).record(step, meter())
    assert not p2_repo.list("alice", "thread")


def test_changed_preflight_cannot_reuse_a_step_receipt(
    p2_repo: PostgresRepository,
) -> None:
    step = completed(p2_repo, "changed", {"input_tokens": 70_000})
    ContextUsageService(p2_repo).record(step, meter())
    with pytest.raises(EvidenceError):
        ContextUsageService(p2_repo).record(step, meter(80_000))
