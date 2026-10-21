"""Opt-in P6 sees proven title/status indexes without selected-case or body access."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.loop_cycle import LoopOutcome
from mingjing_core.agent.runtime_config import RuntimeConfigError, load_runtime_config
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.p6_projection import trusted_records
from mingjing_core.application.p6_validation import P6ValidationBridge
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .case_status_write_support import prepare_write
from .test_case_index_lineage_pg import existing_case
from .test_historical_case_index_pg import prepared_history
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime, submit

CASE_KEYS = {"id", "title", "status", "revision", "subject_id", "entity_kind"}


@pytest.fixture(name="projection_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def outcome(prepared: tuple[Any, ...]) -> LoopOutcome:
    return LoopOutcome(
        "只读事项索引〔e1〕",
        None,
        (),
        copy.deepcopy(prepared[3]),
        dict(prepared[4]),
        {},
        "completed",
    )


@pytest.mark.parametrize("status", ["open", "paused", "closed", "done", "archived"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_real_runtime_p6_keeps_only_proven_case_index_title_and_status(
    projection_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    duplicate: bool,
) -> None:
    repo = projection_repo
    case, original = existing_case(repo)
    if status != case["status"]:
        case = repo.update(
            "alice",
            "case",
            case["id"],
            {"status": status},
            expected_revision=case["revision"],
        )
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    run = repo.claim_run(
        "alice",
        submit(intake, thread, "那件事的进展，只看看合成历史事项的标题和状态")["id"],
    )
    seen: list[dict[str, Any]] = []

    def capture(*args: Any) -> dict[str, dict]:
        records = trusted_records(*args)
        seen.extend(row for row in records.values() if row["entity_kind"] == "case")
        return records

    monkeypatch.setattr("mingjing_core.application.p6_validation.trusted_records", capture)
    calls = [ToolCall("index", "case_list", {})]
    if duplicate:
        calls.append(ToolCall("same-index", "case_list", {}))
    port = ScriptedPort([answer("", calls), answer("只读事项索引〔e1〕")])
    runtime = AgentRuntime(
        repo,
        port,
        SyntheticMeter(),
        offline=True,
        runtime_config=load_runtime_config(),
        p6_validation=P6ValidationBridge(repo),
    )
    result = runtime.execute(intake.service, "alice", run["id"], run["lease_token"])
    assert result["text"] == "只读事项索引〔e1〕" and result["meta"]["case_ids"] == []
    assert seen and all(set(row) == CASE_KEYS and row["status"] == status for row in seen)
    assert original["content"] not in json.dumps(seen, ensure_ascii=False)
    current = repo.fetch_run("alice", run["id"])
    assert "message:" + original["id"] not in current["state_version"]
    assert repo.get("alice", "case", case["id"])["revision"] == case["revision"]


@pytest.mark.parametrize("status", ["open", "done"])
@pytest.mark.parametrize(
    "change",
    ["basis", "index_only", "run_id", "epoch", "seq", "projection", "revision"],
)
def test_alias_self_report_cannot_authorize_p6_index(
    projection_repo: PostgresRepository, status: str, change: str
) -> None:
    prepared = prepared_history(projection_repo, status=status)
    value = outcome(prepared)
    updates = {
        "basis": {"basis": "invented"},
        "index_only": {"index_only": False},
        "run_id": {"run_id": "foreign"},
        "epoch": {"epoch": True},
        "seq": {"model_tool_seq": True},
        "projection": {"index_projection_sha256": "0" * 64},
        "revision": {"revision": 999},
    }
    value.alias_map["e1"].update(updates[change])
    with pytest.raises(CoreError):
        trusted_records(projection_repo, prepared[0].run, value)


@pytest.mark.parametrize("status", ["open", "done"])
@pytest.mark.parametrize("change", ["started", "old_epoch", "projection", "invalid_output", "missing"])
def test_p6_requires_the_real_completed_index_step(
    projection_repo: PostgresRepository, status: str, change: str
) -> None:
    prepared = prepared_history(projection_repo, status=status)
    h = prepared[0]
    with projection_repo.transaction("alice") as connection:
        changes = {
            "started": "status='started',finished_at=NULL",
            "old_epoch": "epoch=epoch+1",
            "projection": "output=jsonb_set(output,'{{data,cases,0,title}}','\"invented\"'::jsonb)",
            "invalid_output": "output='{{}}'::jsonb",
        }
        statement = (
            "DELETE FROM {} WHERE run_id=%s"
            if change == "missing"
            else ("UPDATE {} SET " + changes[change] + " WHERE run_id=%s")
        )
        connection.execute(
            sql.SQL(statement).format(projection_repo.table("core_run_steps")),
            (h.run["id"],),
        )
    with pytest.raises(CoreError):
        trusted_records(projection_repo, h.run, outcome(prepared))


@pytest.mark.parametrize("change", ["revision", "revoked", "subject", "run_owner", "run_epoch", "private"])
def test_p6_does_not_borrow_changed_scope_or_withdrawn_case_proof(
    projection_repo: PostgresRepository, change: str
) -> None:
    prepared = prepared_history(projection_repo)
    h, case = prepared[:2]
    run = copy.deepcopy(h.run)
    if change == "revision":
        projection_repo.update(
            "alice",
            "case",
            case["id"],
            {"title": "真实新标题"},
            expected_revision=case["revision"],
        )
    elif change == "run_owner":
        run["owner"] = "bob"
    elif change == "run_epoch":
        run["retry_epoch"] += 1
    else:
        if change == "subject":
            projection_repo.create_subject("alice", "other", "合成另一个人物")
        with projection_repo.transaction("alice") as connection:
            if change == "revoked":
                projection_repo.revoke(connection, "alice", "case", case["id"], "synthetic_withdrawal")
            elif change == "subject":
                connection.execute(
                    sql.SQL("UPDATE {} SET subject='other' WHERE kind='case' AND id=%s").format(
                        projection_repo.table("core_entities")
                    ),
                    (case["id"],),
                )
            else:
                connection.execute(
                    sql.SQL(
                        "UPDATE {} SET thread_id='incognito:synthetic',"
                        "request=jsonb_set(request,'{{incognito}}','true'::jsonb) WHERE id=%s"
                    ).format(projection_repo.table("core_runs")),
                    (run["id"],),
                )
    with pytest.raises(CoreError):
        trusted_records(projection_repo, run, outcome(prepared))


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_real_selected_status_write_keeps_exact_p3_own_write_proof(
    projection_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    prepared = prepare_write(projection_repo, monkeypatch, status)
    inputs = prepared.inputs
    value = LoopOutcome(
        inputs["text"],
        None,
        (),
        inputs["alias_map"],
        inputs["versions"],
        {},
        "completed",
    )
    records = trusted_records(projection_repo, prepared.run, value)
    assert set(records["e1"]) == CASE_KEYS and records["e1"]["status"] == status
    assert prepared.finish()["text"] == "事项状态已更新〔e1〕"


def test_constructor_preserves_both_trusted_options_and_default_off(
    projection_repo: PostgresRepository,
) -> None:
    args = (projection_repo, ScriptedPort([]), SyntheticMeter())
    runtime = AgentRuntime(*args, offline=True, runtime_config=load_runtime_config())
    assert runtime.p6_validation is None
    with pytest.raises(RuntimeConfigError):
        AgentRuntime(*args, offline=True, runtime_config={})
    with pytest.raises(EvidenceError):
        AgentRuntime(*args, offline=True, p6_validation=SimpleNamespace(repo=projection_repo))


@pytest.mark.parametrize("status", ["done", "archived"])
def test_non_case_cannot_borrow_historical_index_status_exception(
    projection_repo: PostgresRepository, status: str
) -> None:
    prepared = prepared_history(projection_repo)
    note = projection_repo.put(
        "alice",
        "note",
        "synthetic-p6-note",
        {"summary": "合成旧笔记", "status": status},
    )
    value = outcome(prepared)
    value.alias_map["e1"].update(kind="note", id=note["id"], revision=note["revision"])
    value.versions[entity_dependency("note", note["id"])] = note["revision"]
    with pytest.raises(EvidenceError):
        trusted_records(projection_repo, prepared[0].run, value)
