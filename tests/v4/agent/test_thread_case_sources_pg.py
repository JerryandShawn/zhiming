"""Authenticated selections reach first persistence without widening an old source."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime


@pytest.fixture(name="case_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def prepare(repo):
    set_runtime(repo, "v4")
    service, thread = ingress(repo)
    case = MemoryService(repo).create_case("alice", "self", "合成认证事项")
    return service, thread, case


def submit(service, thread, cases, *, request="selected-source", message="合成目标"):
    return service.submit(owner="alice", thread_id=thread, message=message, request_id=request, case_ids=cases)


def state(repo):
    hashes = []
    for name in (
        "core_owners",
        "core_subjects",
        "core_versions",
        "core_entities",
        "core_runs",
        "core_run_steps",
        "core_run_events",
        "core_mutation_requests",
        "core_operations",
        "core_revocations",
    ):
        with repo.transaction() as connection:
            rows = connection.execute(
                sql.SQL('SELECT to_jsonb(t) AS row FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(
                    repo.table(name)
                )
            ).fetchall()
        hashes.append(fingerprint(rows))
    return hashes


def test_first_submit_and_identical_replay_bind_the_same_verified_case_scope(case_repo):
    repo = case_repo
    service, thread, case = prepare(repo)
    run = submit(service, thread, [case["id"], case["id"]])
    source = repo.get("alice", "message", run["request"]["source_message_id"])
    assert source["case_ids"] == run["request"]["case_ids"] == [case["id"]]
    assert run["runtime"] == "v4" and run["status"] == "queued" and run["calls"] == 0
    assert run["request"]["source_message_ids"] == [source["id"]]
    assert run["request"]["source_segments"] == [
        {"message_id": source["id"], "version": source["revision"], "start": 0, "end": len(source["content"])}
    ]
    ident = "privacy-route:" + fingerprint(["alice", "web", "selected-source"])[:32]
    route = repo.get("alice", "request", ident)
    identity = ["self", "web", None, "shared", thread, fingerprint("合成目标"), None]
    assert route["input_fp"] == fingerprint(identity + [{"case_ids": [case["id"]]}])
    before = state(repo)
    again = submit(service, thread, [case["id"]])
    assert again["id"] == run["id"] and repo.get("alice", "message", source["id"]) == source
    assert state(repo) == before


@pytest.mark.parametrize("change", ["replay_selection", "cross_owner", "cross_subject", "revoked"])
def test_changed_or_unauthorized_selection_is_rejected_before_persistence(case_repo, change):
    repo = case_repo
    service, thread, case = prepare(repo)
    if change == "replay_selection":
        submit(service, thread, [case["id"]])
        other = MemoryService(repo).create_case("alice", "self", "合成另一事项")
        choices = [[other["id"]], []]
    elif change == "cross_owner":
        other = MemoryService(repo).create_case("bob", "self", "合成他人事项")
        choices = [[other["id"]]]
    elif change == "cross_subject":
        repo.create_subject("alice", "relative", "合成人物")
        other = MemoryService(repo).create_case("alice", "relative", "合成其他人物事项")
        choices = [[other["id"]]]
    else:
        repo.delete("alice", "case", case["id"], expected_revision=case["revision"])
        assert repo.is_revoked("alice", "case", case["id"])
        choices = [[case["id"]]]
    before = state(repo)
    for selected in choices:
        with pytest.raises(CoreError):
            submit(service, thread, selected)
        if change == "replay_selection":
            with pytest.raises(CoreError):
                ThreadService(repo).receive(
                    "alice", thread, "合成目标", request_id="selected-source", case_ids=selected
                )
        assert state(repo) == before


def test_existing_empty_scope_cannot_gain_case_write_authority_from_queue(case_repo):
    repo = case_repo
    service, thread, case = prepare(repo)
    source = service.receive(owner="alice", thread_id=thread, message="合成目标", request_id="empty-source")
    route = repo.get("alice", "request", "privacy-route:" + fingerprint(["alice", "web", "empty-source"])[:32])
    assert route["input_fp"] == fingerprint(["self", "web", None, "shared", thread, fingerprint("合成目标"), None])
    before = state(repo)
    assert (
        service.receive(owner="alice", thread_id=thread, message="合成目标", request_id="empty-source", case_ids=[])
        == source
    )
    assert state(repo) == before
    queued = service.queue(
        owner="alice", thread_id=thread, source_ids=[source["id"]], request_id="old-source-queue", case_ids=[case["id"]]
    )
    assert queued["request"]["case_ids"] == [case["id"]]
    assert repo.get("alice", "message", source["id"]) == source and source["case_ids"] == []
    run = repo.claim_run("alice", queued["id"])
    versions = {"message:" + source["id"]: source["revision"], entity_dependency("case", case["id"]): case["revision"]}
    repo.set_run_dependencies("alice", run["id"], versions, run["lease_token"])
    registry, journal = ToolRegistry(AgentToolsService(repo)), Journal(repo, "alice")
    args = {
        "id": case["id"],
        "message_id": source["id"],
        "quote": "合成目标",
        "expected_revision": case["revision"],
        "changes": {"goal": "合成目标"},
    }
    step = journal.next_or_replay(
        run,
        kind="tool",
        name="case_update",
        input_fp=registry.fingerprint("case_update", args, source_versions=versions),
    )
    ctx = ToolContext.from_step(
        step, thread_id=thread, source_ids=(source["id"],), case_ids=(case["id"],), source_versions=versions
    )
    result = registry.execute("case_update", args, ctx)
    assert not result.ok and result.data["code"] == "AUTH_SCOPE_ERROR"
    assert repo.get("alice", "case", case["id"]) == case and repo.get("alice", "message", source["id"]) == source
    repo.fail_run("alice", run["id"], "合成组件已核验", run["lease_token"], status="cancelled")


@pytest.mark.parametrize("mode", ["existing_private", "enter_command"])
def test_private_selection_rolls_back_before_any_original_or_route_persists(case_repo, mode):
    repo = case_repo
    service, thread, case = prepare(repo)
    if mode == "existing_private":
        thread = ThreadService(repo).create("alice", incognito=True, request_id="private-case")["id"]
    before = state(repo)
    with pytest.raises(CoreError):
        submit(service, thread, [case["id"]], message="开个无痕" if mode == "enter_command" else "合成目标")
    assert state(repo) == before
