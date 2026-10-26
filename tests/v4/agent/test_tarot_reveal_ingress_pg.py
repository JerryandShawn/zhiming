"""Product intake binds only an explicitly revealed owner/case draw."""

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.adapters.web import create_app
from mingjing_core.application.tarot_reveal_ingress import TarotRevealIngress
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.models.port import ToolCall
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenario
from tools.eval.targets.v4_target import V4Target

from .test_dispatcher_pg import until
from .test_loop_cycle_support import answer
from .test_runtime_assembly_pg import ScriptedPort, configure, service
from .test_thread_routes_pg import HEADERS
from .test_thread_routes_pg import repository_fixture as source_http_fixture


def seeded(core, *, reveal=True):
    question = "这次合成面试能顺利吗"
    source = core.memory.receive("alice", "self", question, source_id="question", channel="web")
    case = core.memory.create_case(
        "alice", "self", question, goal=question, message_id=source["id"], operation_id="case"
    )
    draw = TarotService(core.repo).create_draw(
        "alice",
        subject_id="self",
        case_id=case["id"],
        question=question,
        spread_id="focus1",
        draw_source="auto",
        idempotency_key="draw",
        context_snapshot={
            "question_message_id": source["id"],
            "source_refs": [
                {"message_id": source["id"], "version": source["revision"]},
            ],
        },
    )["draw"]
    if reveal:
        TarotService(core.repo).reveal("alice", draw["id"])
    return draw


def test_reveal_ingress_preserves_original_and_idempotent_binding(p2_repo):
    configure(p2_repo)
    core = service(p2_repo, ScriptedPort([]))
    draw = seeded(core)
    values = dict(owner="alice", draw_id=draw["id"], request_id="reveal", message="揭好了，关注面试准备")
    run = TarotRevealIngress(core).submit(**values)
    again = TarotRevealIngress(core).submit(**values)
    assert again["id"] == run["id"] and run["runtime"] == "v4"
    assert run["request"]["draw_id"] == draw["id"]
    assert run["request"]["case_ids"] == [draw["case_id"]]
    source = core.memory.get_source("alice", run["request"]["source_message_id"])
    assert source["content"] == values["message"] and source["thread_id"] == "life:self"
    assert len([m for m in p2_repo.list("alice", "message") if m.get("content") == values["message"]]) == 1


@pytest.mark.parametrize("invalid", ["owner", "thread", "case", "unrevealed", "revoked"])
def test_reveal_ingress_rejects_scope_before_receiving_message(p2_repo, invalid):
    configure(p2_repo)
    core = service(p2_repo, ScriptedPort([]))
    draw = seeded(core, reveal=invalid != "unrevealed")
    values = dict(owner="alice", draw_id=draw["id"], request_id="denied", message="不应写入")
    if invalid == "owner":
        values["owner"] = "bob"
    elif invalid == "thread":
        values["thread_id"] = "incognito:fixture"
    elif invalid == "case":
        values["case_ids"] = ["other-case"]
    elif invalid == "revoked":
        TarotService(p2_repo).delete("alice", draw["id"])
    before = p2_repo.get_revision(values["owner"])
    with pytest.raises((ScopeError, EvidenceError)):
        TarotRevealIngress(core).submit(**values)
    assert p2_repo.get_revision(values["owner"]) == before


def test_legacy_chat_draw_uses_same_authenticated_ingress(p2_repo):
    configure(p2_repo)
    core = service(p2_repo, ScriptedPort([]))
    draw = seeded(core)
    run = core.submit(owner="alice", request_id="chat-reveal", message="帮我解释这副牌", draw_id=draw["id"])
    assert run["runtime"] == "v4" and run["request"]["draw_id"] == draw["id"]
    with pytest.raises(EvidenceError):
        core.submit(owner="alice", request_id="still-denied", message="附件", draw_id=draw["id"], images=["image"])


@pytest.fixture
def reveal_http_repo(p2_repo, monkeypatch):
    yield from source_http_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("route", ["chat", "panel", "thread"])
def test_authenticated_product_endpoints_execute_the_bound_draw(reveal_http_repo, route):
    repo = reveal_http_repo
    configure(repo)
    port = ScriptedPort([answer("", [ToolCall("read", "tarot_read", {})]), answer("用面试准备检验这份反思。")])
    core = service(repo, port)
    draw = seeded(core)
    with TestClient(create_app(core)) as client:
        if route == "panel":
            url = f"/api/tarot/draws/{draw['id']}/readings"
            payload = {"request_id": "endpoint", "supplement": "关注面试准备"}
        else:
            if route == "thread":
                thread = client.post("/api/threads", headers=HEADERS, json={"request_id": "life"}).json()["id"]
                url = f"/api/threads/{thread}/messages"
            else:
                url = "/api/chat"
            payload = {"request_id": "endpoint", "message": "关注面试准备", "draw_id": draw["id"]}
        response = client.post(url, headers=HEADERS, json=payload)
        assert response.status_code == (202 if route == "thread" else 200)
        until(lambda: len(port.requests) == 2)
        assert any("本轮用户已揭示牌阵" in m.content for m in port.requests[0]["messages"] if m.role == "system")
        assert any(m.role == "tool" and draw["id"] in m.content for m in port.requests[1]["messages"])
        assert core.runtime_assembly.legacy.calls == []


@pytest.mark.parametrize("identity", ["TA01", "TA02", "TA03", "TA04", "AX01"])
def test_reveal_script_contracts(identity, p2_repo):
    target = V4Target()
    try:
        folder = {"AX01": "scenarios_v4_core30", "TA04": "scenarios_v4_batch2"}.get(identity, "scenarios_v4")
        observed = evaluate_scenario(load_scenario(f"tools/eval/{folder}/{identity}.yaml"), target, target_name="v4")
        assert observed["status"] == "passed", observed["failed_assertions"]
        evidence = target.case_evidence()["tool_visibility_by_turn"]
        assert evidence
        if identity == "TA04":
            assert all("tarot_read" not in names for turn in evidence for names in turn["visible_tools_per_request"])
    finally:
        target.close()
