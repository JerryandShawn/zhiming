"""Known unsupported revision chain; keep real assertions without an xfail."""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="chain_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_two_true_case_writes_then_original_alias_requires_a_full_revision_chain(
    chain_repo: PostgresRepository, status: str
) -> None:
    repo = chain_repo
    case, _ = existing_case(repo)
    text = "目标改成合成新计划，然后请" + ("暂停" if status == "paused" else "关闭") + "这件事项"
    run = selected_run(repo, case["id"], text)
    common = {"id": case["id"], "message_id": run["request"]["source_message_id"], "quote": text}
    first = dict(common, expected_revision=case["revision"], changes={"goal": "合成新计划"})
    second = dict(common, expected_revision=case["revision"] + 1, changes={"status": status})
    port = ScriptedPort(
        [
            answer("", [ToolCall("goal", "case_update", first)]),
            answer("", [ToolCall("status", "case_update", second)]),
            answer("事项已完成两次更新〔e1〕"),
        ]
    )
    try:
        envelope = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
            SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
        )
    except CoreError:
        row = repo.get("alice", "case", case["id"])
        assert row["revision"] == case["revision"] + 2 and row["status"] == status
        assert row["state"]["goal"] == "合成新计划" and len(port.requests) == 3
        assert repo.fetch_run("alice", run["id"])["result"] is None
        assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
        raise
    assert envelope["text"] == "事项已完成两次更新〔e1〕"
