"""Pause the actual Runtime immediately before final commit to audit persisted proofs."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer


class BeforeFinal(BaseException):
    pass


@dataclass
class PreparedWrite:
    repo: PostgresRepository = field(repr=False)
    run: dict[str, Any] = field(repr=False)
    inputs: dict[str, Any] = field(repr=False)
    case: dict[str, Any] = field(repr=False)

    def finish(self) -> dict[str, Any]:
        return AgentFinalizer(self.repo).finalize(self.run, **self.inputs)

    def unpublished(self) -> None:
        assert self.repo.fetch_run("alice", self.run["id"])["result"] is None
        assert not [row for row in self.repo.list("alice", "message") if row.get("role") == "assistant"]


def prepare_write(repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, status: str = "closed") -> PreparedWrite:
    case, _ = existing_case(repo)
    text = "请暂停合成索引事项" if status == "paused" else "请关闭合成索引事项"
    run = selected_run(repo, case["id"], text)
    args = {
        "id": case["id"],
        "expected_revision": case["revision"],
        "message_id": run["request"]["source_message_id"],
        "quote": text,
        "changes": {"status": status},
    }
    port = ScriptedPort([answer("", [ToolCall("real-update", "case_update", args)]), answer("事项状态已更新〔e1〕")])
    prepared: list[PreparedWrite] = []

    def pause(self: Any, actual: Any, **inputs: Any) -> dict[str, Any]:
        prepared.append(PreparedWrite(repo, copy.deepcopy(actual), copy.deepcopy(inputs), case))
        raise BeforeFinal()

    with monkeypatch.context() as scope:
        scope.setattr(AgentFinalizer, "finalize", pause)
        with pytest.raises(BeforeFinal):
            AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
                SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
            )
    assert len(prepared) == 1 and len(port.requests) == 2
    changed = repo.get("alice", "case", case["id"])
    assert changed["status"] == status and changed["revision"] == case["revision"] + 1
    prepared[0].unpublished()
    return prepared[0]


def change_step(prepared: PreparedWrite, sequence: int, field_name: str, value: Any) -> None:
    assert field_name in {"status", "error_code", "finished_at", "output"}
    with prepared.repo.transaction("alice") as connection:
        if field_name == "output":
            value = Jsonb(value)
        connection.execute(
            sql.SQL("UPDATE {} SET {}=%s WHERE owner='alice' AND run_id=%s AND seq=%s").format(
                prepared.repo.table("core_run_steps"), sql.Identifier(field_name)
            ),
            (value, prepared.run["id"], sequence),
        )


def corrupt_private(prepared: PreparedWrite, suffix: str, *, remove: bool = False) -> None:
    ident = f"{prepared.run['id']}:e{prepared.run['retry_epoch']}:{suffix}"
    with prepared.repo.transaction("alice") as connection:
        statement = (
            "DELETE FROM {} WHERE owner='alice' AND kind='runtime_step' AND id=%s"
            if remove
            else "UPDATE {} SET data=jsonb_set(data,'{{output_sha256}}','\"bad\"'::jsonb) "
            "WHERE owner='alice' AND kind='runtime_step' AND id=%s"
        )
        result = connection.execute(sql.SQL(statement).format(prepared.repo.table("core_entities")), (ident,))
        assert result.rowcount == 1
