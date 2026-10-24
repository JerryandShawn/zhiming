"""Unfixed reproduction: a legal selected-case status write must retain its own citation."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="own_status_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_current_selected_case_status_write_keeps_original_reference(
    own_status_repo: PostgresRepository, status: str
) -> None:
    repo = own_status_repo
    case, _ = existing_case(repo)
    text = "请把合成索引事项暂停" if status == "paused" else "请把合成索引事项关闭"
    run = selected_run(repo, case["id"], text)
    arguments = {
        "id": case["id"],
        "expected_revision": case["revision"],
        "message_id": run["request"]["source_message_id"],
        "quote": text,
        "changes": {"status": status},
    }
    port = ScriptedPort(
        [answer("", [ToolCall("update-status", "case_update", arguments)]), answer("事项状态已更新〔e1〕")]
    )
    try:
        envelope = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
            SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
        )
    except CoreError:
        changed = repo.get("alice", "case", case["id"])
        assert changed["status"] == status and changed["revision"] == case["revision"] + 1
        with repo.transaction("alice") as connection:
            steps = connection.execute(
                sql.SQL("SELECT status,output FROM {} WHERE run_id=%s AND name='case_update'").format(
                    repo.table("core_run_steps")
                ),
                (run["id"],),
            ).fetchall()
        assert len(steps) == 1 and steps[0]["status"] == "completed"
        assert steps[0]["output"]["receipt"] == {
            "write_status": "saved",
            "kind": "case",
            "id": case["id"],
            "revision": changed["revision"],
        }
        assert repo.fetch_run("alice", run["id"])["result"] is None and len(port.requests) == 2
        assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
        raise
    assert envelope["text"] == "事项状态已更新〔e1〕" and envelope["meta"]["case_ids"] == [case["id"]]
