"""Actual P8 publication followed by a later native context, without stale aliases."""

from copy import deepcopy
import json
import uuid

from psycopg import sql
import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.p8_profile_text import profile_text
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.timekit.clock import get_clock

from . import test_p8_agent_charts_pg as chart_tests
from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare


@pytest.fixture(name="repo")
def repository(p2_repo, monkeypatch):
    return chart_tests.repository.__wrapped__(p2_repo, monkeypatch)


def archive(repo):
    h, _, _, _ = chart_tests.registered(repo)
    h.finish()
    run, registry, frozen = prepare(repo, "查看合成八字，保留口径限制")
    port = ScriptedPort(
        [
            answer("", [ToolCall("p8-call", "chart_compute", {"system": "bazi", "target": "2026-10-17"})]),
            answer("原生盘面〔c1〕与规则〔r1〕仅供参考。"),
        ]
    )
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed"
    AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    assert repo.fetch_run("alice", run["id"])["status"] == "succeeded"
    doc = next(row for row in repo.list("alice", "artifact") if row.get("p8_document"))
    cache = next(
        row
        for row in repo.list("alice", "runtime_step")
        if row.get("tool_output", {}).get("data", {}).get("adapter_mode") == "p8_v1_1"
    )
    return run, doc, cache


def later_context(repo, owner="alice"):
    memory = MemoryService(repo)
    source = memory.receive(
        owner, content="继续讨论现实安排，不在本轮重新排盘", source_id=uuid.uuid4().hex, at=get_clock().now()
    )
    return ContextEngine(memory, "合成摘要测试系统", clock=get_clock()).build(owner, source["id"])


def summaries(built):
    return [
        item
        for layer in built.budget.layers
        for item in layer.items
        if any("<命理档案摘要>" in message.content for message in item.messages)
    ]


def test_published_archive_enters_later_stable_layer_with_native_dependency_closure_and_no_aliases(repo):
    _, doc, cache = archive(repo)
    built = later_context(repo)
    items = summaries(built)
    assert len(items) == 1
    value = json.loads(items[0].messages[0].content.split("\n")[1])["text"]
    assert 0 < len(value) <= 400
    assert all(term in value for term in ("命理档案v", "格局仅筛选候选", "旺衰", "喜用候选", "非本轮计算依据"))
    assert "〔c" not in value and "〔r" not in value
    assert not any(key.startswith(("c", "r")) for key in built.alias_map)
    assert built.injected_versions[entity_dependency("artifact", doc["id"])] == doc["revision"]
    assert built.injected_versions[entity_dependency("runtime_step", cache["id"])] == cache["revision"]
    assert not any(key.startswith(("owner:", "subject:", "global:", "case:")) for key in built.injected_versions)
    assert repo.verify_versions("alice", built.injected_versions)
    old_versions = dict(built.injected_versions)
    repo.update(
        "alice",
        "runtime_step",
        cache["id"],
        {"input_fp": "0" * 64},
        expected_revision=cache["revision"],
        operation_id="change-cache",
    )
    assert not repo.verify_versions("alice", old_versions)
    assert summaries(later_context(repo)) == []


@pytest.mark.parametrize("mode", ["document", "profile", "source", "unfinished", "foreign_owner"])
def test_stale_unfinished_foreign_or_withdrawn_archives_never_become_profile_context(repo, mode):
    run, doc, _ = archive(repo)
    if mode == "document":
        altered = deepcopy(doc["p8_document"])
        altered["payload"]["charts"][0]["data"]["pillars"]["day"] = "甲子"
        repo.update(
            "alice",
            "artifact",
            doc["id"],
            {"p8_document": altered},
            expected_revision=doc["revision"],
            operation_id="tamper-doc",
        )
    elif mode in {"profile", "source"}:
        fact = repo.list("alice", "fact")[0]
        kind, row = (
            ("fact", fact)
            if mode == "profile"
            else ("message", repo.get("alice", "message", fact["source_refs"][0]["message_id"]))
        )
        repo.update(
            "alice", kind, row["id"], {"status": "deleted"}, expected_revision=row["revision"], operation_id="withdraw"
        )
    elif mode == "unfinished":
        with repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET status='failed' WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
                ("alice", run["id"]),
            )
    assert summaries(later_context(repo, "bob" if mode == "foreign_owner" else "alice")) == []


def test_native_formatter_never_fills_missing_or_oversized_candidates(repo):
    _, doc, _ = archive(repo)
    document = doc["p8_document"]
    before = deepcopy(document)
    assert profile_text(document, True) is None
    assert profile_text(document, doc["revision"])
    assert document == before
    document["payload"]["time_basis"]["requires_confirmation"] = True
    assert profile_text(document, doc["revision"]) is None
    document["payload"]["time_basis"]["requires_confirmation"] = False
    chart = next(
        row
        for row in document["payload"]["charts"]
        if row.get("visible_by_default") and row["time_basis"]["basis"] == "true_solar"
    )
    chart["data"]["p8"]["school"] = "很长的待核口径" * 100
    assert profile_text(document, doc["revision"]) is None
