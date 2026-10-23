"""Build genuine multi-write Runtime proofs and pause only before final commit."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_case_effect_records import effect_id
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .case_status_write_support import BeforeFinal, PreparedWrite
from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer


def prepare_chain(
    repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str = "closed",
    count: int = 2,
    same_response: bool = False,
) -> PreparedWrite:
    case, _ = existing_case(repo)
    text = "先把目标改成合成新计划，再改成合成终版计划，最后" + ("暂停" if status == "paused" else "关闭") + "这件事项"
    run = selected_run(repo, case["id"], text)
    changes = [{"goal": "合成新计划"}, {"goal": "合成终版计划"}, {"status": status}]
    changes = changes if count == 3 else [changes[0], changes[-1]]
    calls = [
        ToolCall(
            f"change-{index}",
            "case_update",
            {
                "id": case["id"],
                "message_id": run["request"]["source_message_id"],
                "quote": text,
                "expected_revision": case["revision"] + index,
                "changes": change,
            },
        )
        for index, change in enumerate(changes)
    ]
    responses = [answer("", calls)] if same_response else [answer("", [call]) for call in calls]
    port = ScriptedPort([*responses, answer("事项多次更新〔e1〕")])
    prepared = []

    def pause(self: Any, actual: Any, **inputs: Any) -> dict[str, Any]:
        prepared.append(PreparedWrite(repo, copy.deepcopy(actual), copy.deepcopy(inputs), case))
        raise BeforeFinal()

    with monkeypatch.context() as scope:
        scope.setattr(AgentFinalizer, "finalize", pause)
        with pytest.raises(BeforeFinal):
            AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
                SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
            )
    assert len(prepared) == 1
    actual = repo.get("alice", "case", case["id"])
    assert actual["revision"] == case["revision"] + count and actual["status"] == status
    return prepared[0]


def effect_row(prepared: PreparedWrite, sequence: int) -> dict[str, Any]:
    return prepared.repo.get("alice", "runtime_step", effect_id(prepared.run["id"], 0, sequence), include_deleted=True)


def replace_effect(prepared: PreparedWrite, sequence: int, output: dict[str, Any]) -> None:
    row = effect_row(prepared, sequence)
    with prepared.repo.transaction("alice") as connection:
        data = connection.execute(
            sql.SQL("SELECT data FROM {} WHERE owner='alice' AND kind='runtime_step' AND id=%s").format(
                prepared.repo.table("core_entities")
            ),
            (row["id"],),
        ).fetchone()["data"]
        data.update(output=output, output_sha256=fingerprint(output))
        connection.execute(
            sql.SQL("UPDATE {} SET data=%s WHERE owner='alice' AND kind='runtime_step' AND id=%s").format(
                prepared.repo.table("core_entities")
            ),
            (Jsonb(data), row["id"]),
        )
