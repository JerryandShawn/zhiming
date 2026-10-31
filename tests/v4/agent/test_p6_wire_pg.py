"""Real copied P6 code runs in the Loop; final PG authority remains strict."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.p6_validation import P6ValidationBridge
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, set_clock
from mingjing_core.validation.p6_candidate import structural
from mingjing_core.validation.p6_candidate.structural_receipts import SAVE_NOTE

from .test_agent_runtime_pg import queued
from .test_agent_runtime_pg import repository_fixture as source_repo_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, writer


@pytest.fixture(name="p6_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def run_text(repo: PostgresRepository, text: str, *, enabled: bool = True, critic: Any = None) -> tuple[dict, dict]:
    run = queued(repo)
    runtime = AgentRuntime(
        repo,
        ScriptedPort([answer(text)]),
        SyntheticMeter(),
        offline=True,
        critic=critic,
        p6_validation=P6ValidationBridge(repo) if enabled else None,
    )
    result = runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"])
    return result, repo.fetch_run("alice", run["id"])


def validation_records(repo: PostgresRepository, ident: str) -> list[dict]:
    return [
        row["output"]
        for row in repo.list("alice", "runtime_step")
        if row.get("run_id") == ident
        and row.get("schema") == "p6-wire-draft-v1"
        and "structural" in row.get("output", {})
    ]


def test_copied_real_module_sources_still_match_frozen_manifest() -> None:
    directory = Path(structural.__file__).parent
    manifest = json.loads((directory / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 11
    assert all(
        hashlib.sha256((directory / name).read_bytes()).hexdigest() == row["sha256"]
        for name, row in manifest["files"].items()
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_real_weekday_fix_is_default_off_and_does_not_claim_critic_review(
    p6_repo: PostgresRepository, enabled: bool
) -> None:
    critic = ScriptedPort([answer('{"verdict":"pass","issues":[]}')])
    result, run = run_text(p6_repo, "2026年10月17日（周五）可以先核对安排。", enabled=enabled, critic=critic)
    assert ("周六" in result["text"]) is enabled and ("周五" in result["text"]) is not enabled
    assert result["review"]["state"] == ("skipped" if enabled else "passed")
    assert len(critic.requests) == (0 if enabled else 1)
    if enabled:
        records = validation_records(p6_repo, run["id"])
        assert any(row["structural"].get("weekday_fixed") == 1 for row in records)
        assert len({row["program_at"] for row in records}) == 1
        assert run["usage"]["agent_runtime"]["p6_validation"]["mode"] == "evidence_only"


def test_unknown_alias_and_false_save_use_actual_structural_module(p6_repo: PostgresRepository) -> None:
    result, run = run_text(p6_repo, "依据〔f999〕，我已经保存了喜欢徒步。")
    assert "f999" not in result["text"] and result["text"].count(SAVE_NOTE) == 1
    codes = {code for row in validation_records(p6_repo, run["id"]) for code in row["structural"]}
    assert {"unknown_alias", "false_receipt"} <= codes


def test_long_free_text_is_not_truncated_for_legacy_schema_projection(p6_repo: PostgresRepository) -> None:
    text = "合成普通答复。" * 3000
    result, run = run_text(p6_repo, text)
    assert result["text"] == text and len(result["text"]) > 6000
    assert all("lint_schema_error" not in row["lint"] for row in validation_records(p6_repo, run["id"]))


def test_lint_only_warns_and_never_rewrites_or_blocks_answer(p6_repo: PostgresRepository) -> None:
    text = "这件事没有风险、完全可逆。"
    result, run = run_text(p6_repo, text)
    assert result["text"] == text
    assert any(row["lint"] for row in validation_records(p6_repo, run["id"]))


def test_lint_failure_does_not_undo_a_real_weekday_fix(
    p6_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("PRIVATE_LINT_BODY")

    monkeypatch.setattr("mingjing_core.application.p6_validation.lint", fail)
    result, run = run_text(p6_repo, "2026年10月17日（周五）可以先核对安排。")
    assert "周六" in result["text"] and "周五" not in result["text"]
    records = validation_records(p6_repo, run["id"])
    assert all(row["lint"] == {"p6_lint_internal_error": 1} for row in records)
    assert "PRIVATE_LINT_BODY" not in json.dumps([result, records], ensure_ascii=False)


def test_relative_date_uses_owner_timezone_with_one_pinned_instant(p6_repo: PostgresRepository) -> None:
    set_clock(FrozenClock(datetime(2026, 10, 17, 16, 30, tzinfo=UTC)))
    with p6_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id='alice'").format(p6_repo.table("core_owners")),
            (Jsonb({"timezone": "America/Los_Angeles"}),),
        )
    result, run = run_text(p6_repo, "今天是10月18日。")
    assert "日期以 10月17日 为准" in result["text"]
    records = validation_records(p6_repo, run["id"])
    assert all(
        row["timezone"] == "America/Los_Angeles" and row["program_at"] == "2026-10-17T16:30:00+00:00" for row in records
    )


@pytest.mark.parametrize("text,noted", [("已保存〔f1〕。", False), ("我已经保存了另一项安排。", True)])
def test_actual_saved_receipt_only_authorizes_its_own_target(
    p6_repo: PostgresRepository, text: str, noted: bool
) -> None:
    repo, run = p6_repo, queued(p6_repo)
    port = ScriptedPort([answer("", [ToolCall("write", "memory_write", writer(run))]), answer(text)])
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True, p6_validation=P6ValidationBridge(repo))
    result = runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"])
    assert (SAVE_NOTE in result["text"]) is noted and len(repo.list("alice", "fact")) == 1


def test_validator_exception_keeps_answer_without_private_exception_body(
    p6_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("PRIVATE_VALIDATOR_BODY synthetic-password")

    monkeypatch.setattr("mingjing_core.application.p6_validation.structural_check", fail)
    result, run = run_text(p6_repo, "合成可继续交付的回答")
    assert result["text"] == "合成可继续交付的回答"
    records = validation_records(p6_repo, run["id"])
    assert all(row["structural"] == {"p6_validation_internal_error": 1} for row in records)
    assert "PRIVATE_VALIDATOR_BODY" not in json.dumps([result, run["usage"], records], ensure_ascii=False)


@pytest.mark.parametrize("change", ["cancel", "withdraw"])
def test_cancel_or_withdraw_during_check_cannot_final(
    p6_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    repo, run = p6_repo, queued(p6_repo)
    memory = MemoryService(repo)
    fact = memory.save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )
    original = structural.structural_check

    def interrupted(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if change == "cancel":
            DispatcherCancellation(repo, RunSignals()).request("alice", run["id"])
        else:
            memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
        return result

    monkeypatch.setattr("mingjing_core.application.p6_validation.structural_check", interrupted)
    runtime = AgentRuntime(
        repo,
        ScriptedPort([answer("尚不能发布的合成回答")]),
        SyntheticMeter(),
        offline=True,
        p6_validation=P6ValidationBridge(repo),
    )
    with pytest.raises(CoreError):
        runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"])
    assert repo.fetch_run("alice", run["id"])["result"] is None
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
