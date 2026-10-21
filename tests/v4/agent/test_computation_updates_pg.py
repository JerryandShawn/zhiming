"""Actual PG source/revision/proposal effects; only external calculation is replaced."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.tools.computation_parameters import MemoryUpdate, ProfileUpdateRequest
from mingjing_core.application.agent_tools_contracts import ToolContext, tool_input_fingerprint
from mingjing_core.application.agent_tools_updates import execute_update
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import SAID_AT, Harness, setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="tool_repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def prior(
    repo: PostgresRepository,
    text: str = "我喜欢早上阅读",
    *,
    kind: str = "preference",
    field: str | None = None,
    value: Any = None,
) -> dict[str, Any]:
    memory = MemoryService(repo)
    source = memory.receive("alice", content=text, source_id=uuid.uuid4().hex, at=SAID_AT)
    return memory.save_fact("alice", "self", source["id"], text, kind, field=field, value=value)


def context(h: Harness, name: str, arguments: dict[str, Any], **flags: Any) -> tuple[dict[str, Any], ToolContext]:
    model = MemoryUpdate if name == "memory_update" else ProfileUpdateRequest
    args = model.model_validate(arguments).model_dump()
    step = h.journal.next_or_replay(h.run, kind="tool", name=name, input_fp=tool_input_fingerprint(name, args))
    return args, ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],), **flags)


def correction(h: Harness, fact: dict[str, Any], **changes: Any) -> tuple[dict[str, Any], ToolContext]:
    return context(
        h,
        "memory_update",
        {
            "fact_id": fact["id"],
            "expected_revision": fact["revision"],
            "message_id": h.source["id"],
            "quote": h.source["content"],
            "summary": "当前合成偏好",
            **changes,
        },
    )


def test_real_correction_replays_without_second_fact_and_keeps_original_source(tool_repo: PostgresRepository) -> None:
    fact = prior(tool_repo)
    h = setup(tool_repo, "更正：我现在喜欢晚上阅读")
    args, ctx = correction(h, fact)
    result = execute_update(h.service, "memory_update", args, ctx)
    repeated = execute_update(h.service, "memory_update", args, ctx)
    assert result.ok and repeated.receipt == result.receipt
    new = tool_repo.get("alice", "fact", result.receipt["id"])
    assert new["content"] == h.source["content"] and new["supersedes_id"] == fact["id"]
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "superseded"
    assert len(tool_repo.list("alice", "fact", include_deleted=True)) == 2
    assert tool_repo.get("alice", "message", fact["source_refs"][0]["message_id"])["content"] == fact["content"]
    assert h.source["content"] not in json.dumps(result.receipt, ensure_ascii=False)


@pytest.mark.parametrize("mode", ["wrong_revision", "old_source", "foreign_fact"])
def test_correction_rejects_changed_or_untrusted_target_source(tool_repo: PostgresRepository, mode: str) -> None:
    fact = prior(tool_repo)
    h = setup(tool_repo, "更正：我现在喜欢晚上阅读")
    if mode == "wrong_revision":
        changes = {"expected_revision": fact["revision"] + 1}
        error = RevisionConflict
    elif mode == "old_source":
        changes = {"message_id": fact["source_refs"][0]["message_id"], "quote": fact["content"]}
        error = ScopeError
    else:
        foreign = MemoryService(tool_repo).receive("bob", content="我喜欢合成蓝色", source_id=uuid.uuid4().hex)
        row = MemoryService(tool_repo).save_fact("bob", "self", foreign["id"], foreign["content"], "preference")
        changes, error = {"fact_id": row["id"], "expected_revision": row["revision"]}, ScopeError
    args, ctx = correction(h, fact, **changes)
    with pytest.raises(error):
        execute_update(h.service, "memory_update", args, ctx)
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"


@pytest.mark.parametrize(
    "text", ["更正：我的存款现在是800元", "请保存我喜欢茶。更正：我的存款现在是800元", "更正：现在没有那么多了"]
)
def test_sensitive_and_profile_corrections_create_pending_proposals(tool_repo: PostgresRepository, text: str) -> None:
    fact = prior(tool_repo, "请保存我的存款为500元", kind="background")
    h = setup(tool_repo, text)
    args, ctx = correction(h, fact, quote=text.split("。")[-1])
    result = execute_update(h.service, "memory_update", args, ctx)
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"
    assert result.receipt["code"] == "sensitive_correction"
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"
    assert len(tool_repo.list("alice", "fact")) == 1


def test_sensitive_correction_uses_current_quote_scoped_save_consent(tool_repo: PostgresRepository) -> None:
    fact = prior(tool_repo, "请保存我的存款为500元", kind="background")
    h = setup(tool_repo, "更正：请保存我的存款现在为800元")
    args, ctx = correction(h, fact)
    result = execute_update(h.service, "memory_update", args, ctx)
    assert result.ok and result.receipt["write_status"] == "saved"
    assert tool_repo.get("alice", "fact", result.receipt["id"])["content"] == h.source["content"]


def test_profile_request_persists_only_request_and_never_saves_birth(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我想核对出生时间")
    args, ctx = context(
        h,
        "profile_update_request",
        {
            "fields": ["birth.solar_datetime", "birth.timezone_offset"],
            "message_id": h.source["id"],
            "quote": h.source["content"],
        },
    )
    result = execute_update(h.service, "profile_update_request", args, ctx)
    repeated = execute_update(h.service, "profile_update_request", args, ctx)
    assert result.receipt == repeated.receipt and result.receipt["write_status"] == "pending_confirmation"
    proposal = tool_repo.get("alice", "proposal", result.receipt["id"])
    assert proposal["fields"] == args["fields"] and proposal["status"] == "pending"
    assert h.service.memory.snapshot("alice")["profile"] == {} and tool_repo.list("alice", "fact") == []


def test_birth_correction_requires_confirmation_even_with_explicit_save_phrase(tool_repo: PostgresRepository) -> None:
    fact = prior(
        tool_repo,
        "请保存我的出生时间为2012-05-03 13:18",
        kind="profile",
        field="birth.solar_datetime",
        value="2012-05-03 13:18",
    )
    h = setup(tool_repo, "更正：请保存我的出生时间为2012-05-03 14:18")
    args, ctx = correction(h, fact)
    result = execute_update(h.service, "memory_update", args, ctx)
    assert not result.ok and result.receipt["code"] == "profile_update_required"
    assert h.service.memory.snapshot("alice")["profile"]["birth.solar_datetime"] == "2012-05-03 13:18"
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"


def test_incognito_and_lost_epoch_do_not_create_updates(tool_repo: PostgresRepository) -> None:
    fact = prior(tool_repo)
    h = setup(tool_repo, "更正：我现在喜欢晚上阅读")
    args, ctx = correction(h, fact)
    from dataclasses import replace

    result = execute_update(h.service, "memory_update", args, replace(ctx, incognito=True))
    assert result.receipt["code"] == "incognito"
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET retry_epoch=1 WHERE id=%s").format(tool_repo.table("core_runs")), (h.run["id"],)
        )
    with pytest.raises(LeaseConflict):
        execute_update(h.service, "memory_update", args, ctx)
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"
    assert tool_repo.list("alice", "proposal") == []


def test_target_ambiguity_requires_confirmation(tool_repo: PostgresRepository) -> None:
    fact = prior(tool_repo)
    prior(tool_repo, "我喜欢蓝色")
    h = setup(tool_repo, "更正：我现在喜欢晚上阅读")
    args, ctx = correction(h, fact)
    result = execute_update(h.service, "memory_update", args, ctx)
    assert result.receipt["code"] == "correction_target_confirmation"
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"


def test_self_adopted_old_fact_uses_existing_stale_contract(tool_repo: PostgresRepository) -> None:
    fact = prior(tool_repo)
    h = setup(tool_repo, "更正：我喜欢早上阅读是记错了，我现在喜欢晚上阅读")
    args, ctx = correction(h, fact)
    tool_repo.set_run_dependencies("alice", h.run["id"], {"fact:" + fact["id"]: fact["revision"]}, h.run["lease_token"])
    result = execute_update(h.service, "memory_update", args, ctx)
    assert result.ok and tool_repo.fetch_run("alice", h.run["id"])["status"] == "stale"
    with pytest.raises(CoreError):
        h.journal.complete(h.journal.next_or_replay(h.run, kind="tool", name="profile_get", input_fp="a" * 64), {})
