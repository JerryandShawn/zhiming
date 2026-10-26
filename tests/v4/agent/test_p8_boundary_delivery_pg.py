"""Two real scripted publications distinguish a delivered explanation from a hint."""

import json

import pytest

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.timekit.clock import get_clock

from . import test_p8_agent_charts_pg as chart_tests
from . import test_p8_boundary_guidance_pg as boundary_tests
from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare


@pytest.fixture(name="repo")
def repository(p2_repo, monkeypatch):
    boundary_tests.boundary_birth.__wrapped__(monkeypatch)
    receive = MemoryService.receive

    def in_shared_conversation(service, *args, **kwargs):
        # This component's prepare/finalizer use the native default "shared".
        # Pin the inbound source to that same conversation, as ThreadIngress does.
        kwargs.setdefault("conversation_id", "shared")
        return receive(service, *args, **kwargs)

    monkeypatch.setattr(MemoryService, "receive", in_shared_conversation)
    return chart_tests.repository.__wrapped__(p2_repo, monkeypatch)


class BoundaryPort(ScriptedPort):
    def __init__(self, *, short=False):
        super().__init__(
            [
                answer("", [ToolCall("boundary-chart", "chart_compute", {"system": "bazi", "target": "2026-10-17"})]),
                answer("待工具完成后根据真实投影填写脚本回答"),
            ]
        )
        self.short = short
        self.guidance = None

    def stream(self, messages, **kwargs):
        if len(self.requests) == 1:
            tool = next(row for row in reversed(messages) if row.role == "tool")
            self.guidance = json.loads(tool.content)["data"]["boundary_guidance"]
            assert self.guidance
            text = (
                "时柱临界，声称之前说过但没有完整说明。"
                if self.short
                else "\n\n".join(row["text"] for row in self.guidance)
            )
            self.responses[1] = answer(text)
        yield from super().stream(messages, **kwargs)


def turn(repo, *, publish=True, short=False):
    run, registry, frozen = prepare(repo, "核对合成八字，保留真实时辰交界说明")
    port = BoundaryPort(short=short)
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed", outcome.stop_reason
    envelope = None
    if publish:
        envelope = AgentFinalizer(repo).finalize(
            run,
            text=outcome.text,
            alias_map=outcome.alias_map,
            versions=outcome.versions,
            snapshot_revision=frozen.snapshot_revision,
            usage=outcome.usage,
        )
    return run, outcome, frozen, port, envelope


def initialize(repo):
    h, _, _, _ = chart_tests.registered(repo)
    h.finish()


def test_full_native_published_explanation_selects_brief_next_turn_and_pins_history_proof(repo):
    initialize(repo)
    first = turn(repo)
    assert all(row["display_mode"] == "full" for row in first[3].guidance)
    second = turn(repo)
    assert all(row["display_mode"] == "brief" and row["already_explained"] for row in second[3].guidance)
    assert all(row["text"] == row["brief_text"] and "前面说明" in row["text"] for row in second[3].guidance)
    ident = first[4]["message_id"]
    assert "message:" + ident in second[1].versions
    assert all(row["previous_publication"]["message_id"] == ident for row in second[3].guidance)
    # Only the second run's c/r are registered; the first run's native claims are read dependencies.
    assert not set(first[4]["used_claim_ids"]) & set(second[4]["used_claim_ids"])
    assert set(second[4]["used_claim_ids"]) <= {row["id"] for row in second[1].alias_map.values()}


@pytest.mark.parametrize(
    "mode", ["not_published", "claim_only", "different_conversation", "profile_revision", "claim_deleted"]
)
def test_unproven_or_changed_explanation_never_suppresses_full_warning(repo, mode):
    initialize(repo)
    first = turn(repo, publish=mode != "not_published", short=mode == "claim_only")
    run = first[0]
    if mode == "not_published":
        repo.fail_run("alice", run["id"], "合成未发布运行结束", run["lease_token"], status="cancelled")
    elif mode == "different_conversation":
        row = repo.get("alice", "message", first[4]["message_id"])
        repo.update(
            "alice",
            "message",
            row["id"],
            {"conversation_id": "another-conversation"},
            expected_revision=row["revision"],
            operation_id="move-conversation",
        )
    elif mode == "profile_revision":
        row = repo.list("alice", "fact")[0]
        repo.update(
            "alice",
            "fact",
            row["id"],
            {"value": row["value"]},
            expected_revision=row["revision"],
            operation_id="reconfirm-profile",
        )
    elif mode == "claim_deleted":
        row = repo.get("alice", "interpretive_claim", first[4]["used_claim_ids"][0])
        repo.update(
            "alice",
            "interpretive_claim",
            row["id"],
            {"status": "deleted"},
            expected_revision=row["revision"],
            operation_id="withdraw-old-claim",
        )
    second = turn(repo)
    assert all(row["display_mode"] == "full" and not row["already_explained"] for row in second[3].guidance)


def test_unrelated_new_background_fact_does_not_change_birth_version_or_repeat_full_warning(repo):
    initialize(repo)
    turn(repo)
    memory = MemoryService(repo)
    text = "请记住我喜欢清淡口味"
    source = memory.receive("alice", content=text, source_id="unrelated-preference", at=get_clock().now())
    assert memory.save_fact("alice", "self", source["id"], "我喜欢清淡口味", "preference")["write_status"] == "saved"
    second = turn(repo)
    assert all(row["display_mode"] == "brief" for row in second[3].guidance)


def test_withdrawal_after_brief_selection_blocks_final_publication(repo):
    initialize(repo)
    first = turn(repo)
    run, outcome, frozen, port, _ = turn(repo, publish=False)
    assert all(row["display_mode"] == "brief" for row in port.guidance)
    row = repo.get("alice", "message", first[4]["message_id"])
    repo.update(
        "alice",
        "message",
        row["id"],
        {"status": "deleted"},
        expected_revision=row["revision"],
        operation_id="withdraw-prior-answer",
    )
    with pytest.raises(CoreError):
        AgentFinalizer(repo).finalize(
            run,
            text=outcome.text,
            alias_map=outcome.alias_map,
            versions=outcome.versions,
            snapshot_revision=frozen.snapshot_revision,
        )
    repo.fail_run("alice", run["id"], "合成撤销后未发布", run["lease_token"], status="cancelled")
