"""Only a current owner/run row can attest a nonzero cursor, even when its body is erased."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from psycopg import sql

from mingjing_core.adapters.thread_events import event_response
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from tests.v4.streaming_integration.event_http_support import decoded
from tests.v4.streaming_integration.test_event_notify_pg import claimed, started, stored


def seeded(repo, owner="alice", *, terminal=True):
    run = claimed(repo, owner)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    events.send("text_delta", {"text": "合成精确游标片段"})
    events.send("text_delta", {"text": "合成第三片段"})
    if terminal:
        repo.fail_run(owner, run["id"], "合成终态", run["lease_token"])
    return run


def test_zero_is_empty_start_but_a_hole_below_maximum_is_not_a_cursor(p2_repo):
    repo, run = p2_repo, claimed(p2_repo)
    reader = RunEventReader(repo, "alice", run["id"])
    reader.validate_cursor(0)
    with pytest.raises(EvidenceError, match="不可用"):
        reader.validate_cursor(1)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    events.send("text_delta", {"text": "合成删除行"})
    events.send("text_delta", {"text": "合成保留行"})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND run_id=%s AND seq=2").format(
                repo.table("core_run_events")
            ),
            ("alice", run["id"]),
        )
    reader.validate_cursor(1)
    reader.validate_cursor(3)
    with pytest.raises(EvidenceError, match="不可用"):
        reader.validate_cursor(2)
    remaining, cursor, done = reader.page(1)
    assert (
        [event["data"]["seq"] for event in remaining] == [3]
        and cursor == 3
        and not done
    )


def test_foreign_number_cannot_fill_current_run_hole_or_reveal_where_it_exists(p2_repo):
    repo, target = p2_repo, seeded(p2_repo)
    other_owner, other_run = seeded(repo, "bob"), seeded(repo)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND run_id=%s AND seq=2").format(
                repo.table("core_run_events")
            ),
            ("alice", target["id"]),
        )
    assert [row["seq"] for row in stored(repo, other_owner)] == [1, 2, 3]
    assert [row["seq"] for row in stored(repo, other_run)] == [1, 2, 3]
    reader, errors = RunEventReader(repo, "alice", target["id"]), []
    for value in (2, 999):
        with pytest.raises(EvidenceError) as caught:
            reader.validate_cursor(value)
        errors.append(str(caught.value))
    assert errors == ["事件游标不可用，请重新读取运行状态"] * 2
    # The same number existing in a different run does not invalidate our actual row.
    reader.validate_cursor(3)
    with pytest.raises(ScopeError):
        RunEventReader(repo, "bob", target["id"])


def test_real_withdrawal_erases_body_but_retains_legal_cursor_and_never_rebuilds_it(
    p2_repo,
):
    repo, run = p2_repo, seeded(p2_repo, terminal=False)
    reader = RunEventReader(repo, "alice", run["id"])
    repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
    assert all(row["payload"] == {} for row in stored(repo, run))
    reader.validate_cursor(1)
    reader.validate_cursor(3)
    actual, last, done = reader.page(1)
    assert len(actual) == 1 and actual[0]["type"] == "error"
    assert actual[0]["data"]["code"] == "SOURCE_REVOKED" and last == 4 and done
    assert all(row["payload"] == {} for row in stored(repo, run)[:3])


def test_invalid_cursor_check_does_not_repair_terminal_or_append_any_event(p2_repo):
    repo, run = p2_repo, seeded(p2_repo)
    before = stored(repo, run)
    reader = RunEventReader(repo, "alice", run["id"])
    with pytest.raises(EvidenceError, match="不可用"):
        reader.validate_cursor(4)
    assert stored(repo, run) == before
    assert (
        repo.fetch_run("alice", run["id"])["usage"].get("event_terminal_error") is None
    )


def test_legacy_bridge_trusted_header_dict_does_not_consume_get_query_aliases(p2_repo):
    repo, run = p2_repo, seeded(p2_repo)

    async def connected():
        return False

    request = SimpleNamespace(
        headers={"Last-Event-ID": "1"},
        query_params={"after": "2"},
        scope={},
        is_disconnected=connected,
    )
    response = event_response(repo, "alice", run["id"], request)

    async def collect():
        return "".join([part async for part in response.body_iterator])

    assert [item["data"]["seq"] for item in decoded(asyncio.run(collect()))] == [
        2,
        3,
        4,
    ]
