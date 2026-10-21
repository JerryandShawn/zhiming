"""Public submit selects privacy before persistence and replays the original scoped route."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from mingjing_core.application.private_retention import retire_private_thread
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.consultation import MissingInput
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort
from .test_runtime_assembly_pg import configure, service
from .test_runtime_assembly_pg import repository_fixture as source_repo_fixture


@pytest.fixture(name="privacy_assembly_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("message", ["开启无痕", "这段别记", "结束无痕"])
def test_v3_explicit_privacy_is_refused_before_original_or_run(
    privacy_assembly_repo: PostgresRepository, message: str
) -> None:
    repo = privacy_assembly_repo
    core = service(repo)
    with pytest.raises(EvidenceError, match="无痕"):
        core.submit(owner="alice", request_id="legacy-private", message=message)
    assert repo.list("alice", "message") == [] and repo.queued_runs("alice") == []


@pytest.mark.parametrize("message", [None, "", "  "])
def test_legacy_invalid_input_still_uses_legacy_domain_error(
    privacy_assembly_repo: PostgresRepository, message: str | None
) -> None:
    core = service(privacy_assembly_repo)
    with pytest.raises(MissingInput):
        core.submit(owner="alice", request_id="invalid-old-input", message=message)


def test_automatic_private_replay_keeps_original_thread_after_owner_runtime_change(
    privacy_assembly_repo: PostgresRepository,
) -> None:
    repo = privacy_assembly_repo
    configure(repo)
    port, message = ScriptedPort([]), "这段别记，我想聊合成困扰"
    core = service(repo, port)
    first = core.submit(owner="alice", request_id="natural-private", message=message)
    assert first["thread_id"].startswith("incognito:") and first["request"]["incognito"] is True
    configure(repo, "v3")
    replay = core.submit(owner="alice", request_id="natural-private", message=message)
    assert replay["id"] == first["id"] and replay["thread_id"] == first["thread_id"] and replay["runtime"] == "v4"
    originals = repo.list("alice", "message")
    assert len(originals) == 1 and originals[0]["thread_id"] == first["thread_id"]
    assert port.requests == [] and core.runtime_assembly.legacy.calls == []


def test_active_private_session_blocks_new_v3_original_but_other_conversation_stays_legacy(
    privacy_assembly_repo: PostgresRepository,
) -> None:
    repo = privacy_assembly_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    first = core.submit(owner="alice", request_id="privacy-mode", message="开启无痕")
    configure(repo, "v3")
    with pytest.raises(EvidenceError, match="无痕"):
        core.submit(owner="alice", request_id="blocked-private", message="合成后续仍应私密")
    assert len(repo.list("alice", "message")) == 1 and len(repo.queued_runs("alice")) == 1
    independent = core.submit(
        owner="alice", request_id="independent", message="合成独立普通问题", conversation_id="other"
    )
    assert independent["runtime"] == "v3" and first["thread_id"].startswith("incognito:")


def test_existing_private_source_never_moves_into_life_when_submitted_explicitly(
    privacy_assembly_repo: PostgresRepository,
) -> None:
    repo = privacy_assembly_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    first = core.submit(owner="alice", request_id="private-original", message="开启无痕")
    second = core.submit(
        owner="alice",
        request_id="private-explicit-source",
        message="开启无痕",
        source_message_id=first["request"]["source_message_id"],
    )
    assert second["thread_id"] == first["thread_id"] and second["request"]["incognito"] is True
    assert len(repo.list("alice", "message")) == 1


def test_closed_private_request_cannot_be_replayed_or_reconstructed(privacy_assembly_repo: PostgresRepository) -> None:
    repo = privacy_assembly_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    first = core.submit(owner="alice", request_id="closed-private", message="开启无痕")
    retire_private_thread(repo, "alice", first["thread_id"], expired_only=False)
    with pytest.raises(EvidenceError, match="原请求"):
        core.submit(owner="alice", request_id="closed-private", message="开启无痕")
    assert repo.list("alice", "message") == [] and repo.fetch_run("alice", first["id"])["status"] == "revoked"


def test_merged_originals_replay_all_scoped_sources_without_joining(privacy_assembly_repo: PostgresRepository) -> None:
    repo = privacy_assembly_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    thread = ThreadService(repo).create("alice", request_id="merged-life")["id"]
    ingress = ThreadIngress(core)
    sources = [
        ingress.receive(owner="alice", thread_id=thread, message=text, request_id="source-" + str(index))
        for index, text in enumerate(["合成第一条原话", "合成第二条原话"])
    ]
    first = ingress.queue(
        owner="alice", thread_id=thread, source_ids=[row["id"] for row in sources], request_id="merged-run"
    )
    replay = core.submit(owner="alice", request_id="merged-run", message=first["request"]["message"])
    assert replay["id"] == first["id"]
    assert replay["request"]["source_message_ids"] == first["request"]["source_message_ids"]
    assert len(replay["request"]["source_segments"]) == len(repo.list("alice", "message")) == 2
