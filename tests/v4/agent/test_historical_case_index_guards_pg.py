"""Historical index exception cannot authorize invented proof, bodies or other kinds."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .test_historical_case_index_pg import prepared_history
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="history_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def finish(prepared: tuple[Any, ...]) -> dict[str, Any]:
    h, _, _, aliases, versions, revision = prepared
    return AgentFinalizer(h.repo, clock=h.service.clock).finalize(
        h.run, text="历史索引〔e1〕", alias_map=aliases, versions=versions, snapshot_revision=revision
    )


def assert_unpublished(repo: PostgresRepository, run_id: str) -> None:
    assert repo.fetch_run("alice", run_id)["result"] is None
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("basis", "invented"),
        ("index_only", False),
        ("index_only", 1),
        ("run_id", "another-run"),
        ("epoch", 1),
        ("model_tool_seq", 2),
        ("model_tool_seq", True),
        ("index_projection_sha256", "0" * 64),
        ("revision", 999),
    ],
)
def test_alias_self_report_cannot_authorize_historical_case(
    history_repo: PostgresRepository, field: str, value: Any
) -> None:
    prepared = prepared_history(history_repo)
    prepared[3]["e1"][field] = value
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(history_repo, prepared[0].run["id"])


@pytest.mark.parametrize(
    "change",
    ["missing", "started", "error", "other_tool", "old_epoch", "other_owner", "invalid_output", "projection"],
)
def test_only_exact_current_completed_case_list_step_can_authorize_history(
    history_repo: PostgresRepository, change: str
) -> None:
    prepared = prepared_history(history_repo)
    h = prepared[0]
    if change == "other_owner":
        source = MemoryService(history_repo).receive(
            "bob", content="另一身份的合成消息", source_id="foreign-case-proof"
        )
        other = history_repo.queue_run(
            "bob", "foreign-case-proof", {"message": source["content"], "source_message_id": source["id"]}
        )
    with history_repo.transaction("alice") as connection:
        changes = {
            "started": "status='started',finished_at=NULL",
            "error": "error_code='synthetic_error'",
            "other_tool": "name='time_context'",
            "old_epoch": "epoch=epoch+1",
            "other_owner": "owner='bob',run_id=%s",
            "invalid_output": "output='{{}}'::jsonb",
            "projection": "output=jsonb_set(output,'{{data,cases,0,title}}','\"invented\"'::jsonb)",
        }
        statement = (
            "DELETE FROM {} WHERE run_id=%s"
            if change == "missing"
            else ("UPDATE {} SET " + changes[change] + " WHERE run_id=%s")
        )
        args = (other["id"], h.run["id"]) if change == "other_owner" else (h.run["id"],)
        connection.execute(sql.SQL(statement).format(history_repo.table("core_run_steps")), args)
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(history_repo, h.run["id"])


@pytest.mark.parametrize("change", ["revision", "deleted", "revoked", "foreign_subject"])
def test_history_index_does_not_bypass_current_revision_or_withdrawal(
    history_repo: PostgresRepository, change: str
) -> None:
    prepared = prepared_history(history_repo)
    h, case = prepared[:2]
    if change == "revision":
        history_repo.update("alice", "case", case["id"], {"title": "真实新标题"}, expected_revision=case["revision"])
    elif change == "deleted":
        history_repo.delete("alice", "case", case["id"], expected_revision=case["revision"])
    else:
        if change == "foreign_subject":
            history_repo.create_subject("alice", "other", "合成另一人物")
        with history_repo.transaction("alice") as connection:
            if change == "revoked":
                history_repo.revoke(connection, "alice", "case", case["id"], "synthetic_withdrawal")
            else:
                connection.execute(
                    sql.SQL("UPDATE {} SET subject='other' WHERE kind='case' AND id=%s").format(
                        history_repo.table("core_entities")
                    ),
                    (case["id"],),
                )
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(history_repo, h.run["id"])


@pytest.mark.parametrize("status", ["closed", "paused", "superseded", "stopped"])
def test_other_case_status_rules_are_unchanged(history_repo: PostgresRepository, status: str) -> None:
    prepared = prepared_history(history_repo)
    h, case, _, aliases, versions, _ = prepared
    changed = history_repo.update("alice", "case", case["id"], {"status": status}, expected_revision=case["revision"])
    versions[entity_dependency("case", case["id"])] = changed["revision"]
    aliases["e1"]["revision"] = changed["revision"]
    history_repo.set_run_dependencies("alice", h.run["id"], versions, h.run["lease_token"])
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(history_repo, h.run["id"])


@pytest.mark.parametrize("status", ["done", "archived"])
def test_non_case_entity_cannot_use_historical_index_exception(history_repo: PostgresRepository, status: str) -> None:
    prepared = prepared_history(history_repo)
    h, _, _, aliases, versions, _ = prepared
    note = history_repo.put("alice", "note", "synthetic-historical-note", {"summary": "旧笔记", "status": status})
    aliases["e1"] = dict(aliases["e1"], kind="note", id=note["id"], revision=note["revision"])
    versions[entity_dependency("note", note["id"])] = note["revision"]
    history_repo.set_run_dependencies("alice", h.run["id"], versions, h.run["lease_token"])
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(history_repo, h.run["id"])
