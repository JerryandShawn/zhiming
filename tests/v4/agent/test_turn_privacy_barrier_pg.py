"""A late opt-out closes all later persistent tool effects of the existing turn."""

from types import SimpleNamespace

import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.port import ToolCall

from .test_agent_runtime_pg import repository_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_turn_sources_runtime_pg import intake


@pytest.fixture(name="barrier_repo")
def repository(p2_repo, monkeypatch):
    yield from repository_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("tool", ["memory_write", "note_write", "set_reminder"])
def test_optout_during_model_io_stops_later_writes_from_earlier_original(barrier_repo, tool):
    repo = barrier_repo
    ingress, thread = intake(repo)
    queued = ingress.submit(owner="alice", thread_id=thread, message="我喜欢合成青杯", request_id="old-turn")
    run = repo.claim_run("alice", queued["id"], lease_seconds=150)
    source = run["request"]["source_message_id"]
    arguments = {
        "memory_write": dict(
            message_id=source, quote=run["request"]["message"], summary="喜欢合成青杯", kind="preference"
        ),
        "note_write": dict(summary="合成观察", source_ids=[source]),
        "set_reminder": dict(text="喝水", due_at="2026-10-19T10:30:00+08:00", message_id=source, quote="合成青杯"),
    }[tool]

    class OptoutPort(ScriptedPort):
        def stream(self, messages, **kwargs):
            if not self.requests:
                child = ingress.submit(owner="alice", thread_id=thread, message="本轮别记", request_id="late-optout")
                assert child["thread_id"].startswith("incognito:")
            yield from super().stream(messages, **kwargs)

    port = OptoutPort([answer("", [ToolCall("late-write", tool, arguments)]), answer("本轮没有长期保存。")])
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    assert result["schema"] == "core4.0"
    assert all(repo.list("alice", kind) == [] for kind in ("fact", "note", "reminder"))
    with repo.transaction("alice") as connection:
        row = connection.execute(
            sql.SQL("SELECT output FROM {} WHERE owner='alice' AND run_id=%s AND name=%s").format(
                repo.table("core_run_steps")
            ),
            (run["id"], tool),
        ).fetchone()
    assert row["output"]["receipt"] == {"write_status": "stopped", "code": "privacy_optout"}
