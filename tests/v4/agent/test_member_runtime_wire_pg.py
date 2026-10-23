"""Physical member attempts get actual worker identity, strict private codec and guard release."""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from models.test_quota_guard_pg import configure_central
from models.test_quota_http_pg import rows
from models.test_u39_anthropic_wire import block_record
from psycopg import sql

from mingjing_core.agent.loop_codec import assistant_from
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import current_scope
from mingjing_core.repositories.postgres import PostgresRepository

from .member_wire_support import member_port, response
from .test_dispatcher_pg import queued, until
from .test_loop_cycle_support import SyntheticMeter


@pytest.fixture(name="wire_guard")
def guard_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> QuotaGuard:
    return QuotaGuard(**configure_central(p2_repo, monkeypatch))


@pytest.mark.parametrize("lane", ["interactive", "background"])
def test_primary_and_critic_use_trusted_scope_inside_actual_worker(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard, lane: str
) -> None:
    repo, seen = p2_repo, []
    run = queued(repo, lane=lane)

    def answer(request: httpx.Request) -> httpx.Response:
        scope = current_scope()
        seen.append((threading.current_thread().name, scope.run_id, scope.lane))
        body = json.loads(request.content)
        assert body["model"] == "k3-256k" and not {"thinking", "temperature", "top_p"} & body.keys()
        return response()

    primary = member_port(wire_guard, answer)
    critic = member_port(
        wire_guard, lambda request: (answer(request), response('{"verdict":"pass","issues":[]}'))[1], role="critic"
    )
    runtime = AgentRuntime(repo, primary, SyntheticMeter(), critic=critic, offline=True)
    from types import SimpleNamespace

    dispatcher = AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime))
    try:
        assert dispatcher.tick() == 1
        until(lambda: repo.fetch_run("alice", run["id"])["status"] == "succeeded", timeout=5)
    finally:
        dispatcher.close()
    assert len(seen) == 2 and all(
        name.startswith("agent-dispatch") and ident == run["id"] and selected == lane for name, ident, selected in seen
    )
    records = rows(wire_guard)
    assert [(row["role"], row["bucket"]) for row in records] == [
        ("primary", "interactive" if lane == "interactive" else "background"),
        ("critic", "critic"),
    ]
    assert all(row["run_id"] == run["id"] and row["lane"] == lane for row in records)
    assert wire_guard.status()["in_flight"] == 0


def test_real_runtime_private_blocks_roundtrip_through_pg_request_codec(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard
) -> None:
    from types import SimpleNamespace

    repo, requests = p2_repo, []
    run = repo.claim_run("alice", queued(repo)["id"])
    blocks = [
        {"type": "thinking", "thinking": "合成私密推理", "signature": "synthetic.signature/A+="},
        {"type": "tool_use", "id": "synthetic:original/A", "name": "time_context", "input": {}},
    ]

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=block_record(blocks)) if len(requests) == 1 else response()

    port = member_port(wire_guard, answer)
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    assistant = next(row for row in requests[1]["messages"] if row["role"] == "assistant")
    assert assistant["content"] == blocks and "合成私密推理" not in json.dumps(result, ensure_ascii=False)
    with repo.transaction("alice") as connection:
        steps = connection.execute(
            sql.SQL("SELECT seq,output FROM {} WHERE run_id=%s AND kind='model' ORDER BY seq").format(
                repo.table("core_run_steps")
            ),
            (run["id"],),
        ).fetchall()
    stored = assistant_from(steps[0]["output"])
    assert (
        stored.private_content == blocks
        and stored.reasoning_signature == "synthetic.signature/A+="
        and stored.reasoning_present
    )
    cached = RequestLedger(repo, SyntheticMeter(), offline=True)._load(
        "alice", run["id"], run["retry_epoch"], steps[1]["seq"]
    )
    assert (
        cached is not None
        and next(row for row in cached.budget.messages if row.role == "assistant").private_content == blocks
    )
    assert port.request_count == len(rows(wire_guard)) == 2 and wire_guard.status()["in_flight"] == 0
