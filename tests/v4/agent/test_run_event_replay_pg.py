"""Real PG races between normal final emission and subscriber recovery are idempotent."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort, answer
from .test_runtime_assembly_pg import configure, service
from .test_runtime_assembly_pg import repository_fixture as source_repo_fixture


@pytest.fixture(name="event_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("ask", [False, True])
def test_subscriber_and_runtime_emit_one_final_and_one_question(event_repo: PostgresRepository, ask: bool) -> None:
    repo = event_repo
    configure(repo)
    question = {
        "question": "合成问题？",
        "options": [],
        "allow_free_text": True,
        "why": "决定建议",
        "slot": "建议因素",
        "changes_conclusion": "影响选择",
    }
    response = answer("", [ToolCall("ask", "ask_user", question)]) if ask else answer("合成终稿")
    core = service(repo, ScriptedPort([response]))
    run = core.submit(owner="alice", request_id="race", message="合成当前问题")
    result = core.execute("alice", run["id"])
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE run_id=%s AND kind IN ('final','ask_user')").format(
                repo.table("core_run_events")
            ),
            (run["id"],),
        )

    def normal() -> None:
        events = RuntimeEvents(repo, run, None)
        if result["asked"]:
            events.send("ask_user", result["asked"])
        events.send("final", {"message_id": result["message_id"], "envelope": result})

    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [executor.submit(normal), executor.submit(RunEventReader(repo, "alice", run["id"]).ensure_terminal)]
        for task in tasks:
            task.result()
    with repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT kind,count(*) AS n FROM {} WHERE run_id=%s AND kind IN ('final','ask_user') GROUP BY kind"
            ).format(repo.table("core_run_events")),
            (run["id"],),
        ).fetchall()
    assert {row["kind"]: row["n"] for row in rows} == ({"final": 1, "ask_user": 1} if ask else {"final": 1})


def test_corrupt_existing_final_cannot_be_overwritten_or_replayed(event_repo: PostgresRepository) -> None:
    repo = event_repo
    configure(repo)
    core = service(repo, ScriptedPort([answer("真实合成终稿")]))
    run = core.submit(owner="alice", request_id="corrupt", message="合成问题")
    result = core.execute("alice", run["id"])
    with repo.transaction("alice") as connection:
        row = connection.execute(
            sql.SQL("SELECT payload FROM {} WHERE run_id=%s AND kind='final'").format(repo.table("core_run_events")),
            (run["id"],),
        ).fetchone()
        value = dict(row["payload"], envelope=dict(result, text="篡改终稿", answer="篡改终稿"))
        connection.execute(
            sql.SQL("UPDATE {} SET payload=%s WHERE run_id=%s AND kind='final'").format(repo.table("core_run_events")),
            (Jsonb(value), run["id"]),
        )
    with pytest.raises(EvidenceError, match="不能覆盖"):
        RunEventReader(repo, "alice", run["id"]).ensure_terminal()
    assert repo.fetch_run("alice", run["id"])["result"]["text"] == "真实合成终稿"


def test_error_replay_is_idempotent_per_attempt_and_retry_gets_new_sequence(event_repo: PostgresRepository) -> None:
    repo = event_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    run = core.submit(owner="alice", request_id="error", message="合成问题")
    claimed = repo.claim_run("alice", run["id"])
    repo.fail_run("alice", run["id"], "synthetic", claimed["lease_token"])
    reader = RunEventReader(repo, "alice", run["id"])
    first, last, _ = reader.page(0)
    assert len(first) == 1 and first[0]["type"] == "error" and reader.page(last)[0] == []
    repo.prepare_retry("alice", run["id"])
    claimed = repo.claim_run("alice", run["id"])
    repo.fail_run("alice", run["id"], "synthetic", claimed["lease_token"])
    second, newer, _ = reader.page(last)
    assert len(second) == 1 and newer > last
    with pytest.raises(EvidenceError, match="游标"):
        reader.validate_cursor(newer + 1)
