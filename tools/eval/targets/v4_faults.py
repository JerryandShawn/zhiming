"""Bounded synthetic faults exercise actual journal recovery and crisis policy."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from psycopg import sql

from mingjing_core.models.errors import ModelBadRequest, ModelQuotaExhausted, ModelUnavailable
from mingjing_core.models.port import ChatMessage, StreamEvent
from mingjing_core.repositories.postgres import PostgresRepository

from .v4_scripted import ScriptedModelPort


class FaultScriptedPort(ScriptedModelPort):
    def __init__(self, *, crash_after_tool: bool = False) -> None:
        super().__init__()
        self.crash_after_tool, self.crashed, self.failure = crash_after_tool, False, None

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        if self.crash_after_tool and not self.crashed and any(message.role == "tool" for message in messages):
            self.crashed = True
            raise SystemExit("synthetic crash after durable tool, before next provider")
        if self.failure:
            self.calls += 1
            failure = {"unavailable": ModelUnavailable, "quota": ModelQuotaExhausted, "blocked": ModelBadRequest}
            if self.failure not in failure:
                raise ValueError("Unknown synthetic provider failure")
            raise failure[self.failure]()
        yield from super().stream(messages, **kwargs)


def reclaim_crashed(repo: PostgresRepository, owner: str, ident: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with repo.transaction(owner) as connection:
        before = repo.fetch_run(owner, ident)
        if before["runtime"] != "v4" or before["status"] != "running" or before["cancel_requested_at"]:
            raise ValueError("Only the exact synthetic crashed run may resume")
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            (owner, ident),
        )
    current = repo.claim_run(owner, ident, lease_seconds=150)
    if current["lease_token"] == before["lease_token"] or current["retry_epoch"] != before["retry_epoch"]:
        raise ValueError("Synthetic recovery did not replace the lease in the same epoch")
    return current, {
        "name": "run.resumed",
        "source_store": "core_runs lease + journal",
        "run_id": ident,
        "epoch": current["retry_epoch"],
        "rule": "exact failed process surrogate; expired old lease -> new claim; no new epoch",
    }


def crash_observations(steps: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    records = [
        {
            "name": "run.step_committed",
            "source_store": "core_run_steps",
            "run_id": run_id,
            "seq": step["seq"],
            "rule": "completed tool persisted before synthetic process exit",
        }
        for step in steps
        if step["status"] == "completed"
    ]
    if not records:
        raise ValueError("Crash surrogate has no committed tool to prove the fault boundary")
    return records + [
        {
            "name": "run.crashed",
            "source_store": "synthetic SystemExit + PG running journal",
            "run_id": run_id,
            "rule": "after tool commit, before next provider",
        }
    ]
