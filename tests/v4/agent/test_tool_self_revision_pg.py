"""A second real tool preserves the frozen fingerprint after a proven own write."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from psycopg import sql

from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_own_revisions_pg import prepared_case
from .test_loop_cycle_support import ScriptedPort, answer, cycle
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="cycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_real_second_tool_accepts_only_proven_own_revisions(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    _, registry, run, frozen, update = prepared_case(repo)
    read = ToolCall("read", "profile_get", {})
    result = cycle(
        ScriptedPort([answer("", [update]), answer("", [read]), answer("合成结束")]), registry, run, frozen
    ).execute()
    assert result.stop_reason == "completed"
    with repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL("SELECT name,output FROM {} WHERE run_id=%s AND kind='tool' ORDER BY seq").format(
                repo.table("core_run_steps")
            ),
            (run["id"],),
        ).fetchall()
    assert [row["name"] for row in rows] == ["case_update", "profile_get"]
    assert all(row["output"]["ok"] for row in rows)
