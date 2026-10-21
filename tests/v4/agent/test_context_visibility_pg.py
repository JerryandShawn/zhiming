"""View changes reset cache identity without weakening same-view L5 immutability."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_types import ContextInputError
from mingjing_core.application.context_epochs import ContextEpochService
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import fingerprint

from .test_context_epochs_pg import finish_component, started
from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive


@pytest.mark.parametrize("cases", [(), ("a",), ("a", "b")])
def test_case_view_identity_is_a_canonical_set(cases: tuple[str, ...]) -> None:
    assert ContextEpochService._visibility(cases) == ContextEpochService._visibility(tuple(reversed(cases)) + cases)


@pytest.mark.parametrize("cases", [("",), (None,), tuple(str(index) for index in range(9))])
def test_invalid_case_view_identity_is_rejected(cases: tuple) -> None:
    with pytest.raises(ContextInputError, match="上下文资料"):
        ContextEpochService._visibility(cases)


def test_view_comparison_does_not_replace_current_source_version_checks() -> None:
    service = ContextEpochService(SimpleNamespace(verify_versions=lambda owner, versions: False))
    view = service._visibility(())
    assert service._view_invalidated("alice", {"visibility_sha256": view, "source_versions": {}}, view)


def test_legacy_cache_without_view_identity_reopens_once_then_appends(memory: MemoryService) -> None:
    repo, engine, service = memory.repo, ContextEngine(memory, "合成系统"), ContextEpochService(memory.repo)
    source = receive(memory, "合成最初一轮", "scope-first")
    context = engine.build("alice", source["id"])
    step = started(memory, source, context, "scope-first")
    service.mark_sent(step, context)
    finish_component(memory, step)
    thread = repo.get("alice", "thread", "life:self")
    cache = dict(thread["context_cache"])
    cache.pop("visibility_sha256")
    repo.update("alice", "thread", thread["id"], {"context_cache": cache}, expected_revision=thread["revision"])

    second = receive(memory, "合成范围身份升级", "scope-second")
    rebuilt = engine.build("alice", second["id"])
    assert rebuilt.cache_epoch.epoch == cache["epoch"] + 1
    assert rebuilt.cache_epoch.reset_reason == "sources_changed"
    next_step = started(memory, second, rebuilt, "scope-second")
    service.mark_sent(next_step, rebuilt)
    finish_component(memory, next_step)
    saved = repo.get("alice", "thread", "life:self")["context_cache"]
    assert saved["visibility_sha256"] == fingerprint({"case_ids": []})

    third = receive(memory, "合成同范围后续", "scope-third")
    appended = engine.build("alice", third["id"])
    assert appended.cache_epoch.epoch == rebuilt.cache_epoch.epoch
    assert appended.cache_epoch.reset_reason is None
