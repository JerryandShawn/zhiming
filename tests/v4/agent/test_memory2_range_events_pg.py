"""M08/TM range events preserve exclusive endpoints and legacy proposal dates."""

from datetime import datetime, timedelta
from typing import Any

import pytest

from mingjing_core.application.memory2_archive import MemoryArchiveService
from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.application.time_range_parser import ModuleTimeRangeParser
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import FrozenClock

from .test_memory2_slots_pg import slots_repo
from .test_toolkit_pg import setup


@pytest.fixture(name="tool_repo")
def range_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize(
    "text,zone,start,end",
    [
        ("我这周参加合成会议", "Asia/Shanghai", "2026-10-11T16:00:00+00:00", "2026-10-18T16:00:00+00:00"),
        ("我上个月参加合成会议", "Asia/Shanghai", "2026-08-31T16:00:00+00:00", "2026-09-30T16:00:00+00:00"),
        ("我这周参加合成会议", "America/Los_Angeles", "2026-10-12T07:00:00+00:00", "2026-10-19T07:00:00+00:00"),
    ],
)
def test_tm_range_write_is_anchored_to_original_clock_and_owner_zone(tool_repo, text, zone, start, end):
    h = setup(tool_repo, text, parser=ModuleTimeRangeParser())
    h.service.timezone = lambda ctx: zone
    result, ctx, args = h.write("event")
    assert result.ok and result.receipt["write_status"] == "saved"
    row = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert row["precision"] == "range" and row["event_at"] == start and row["event_end"] == end
    assert row["owner_timezone"] == zone and row["source_refs"][0]["quote"] == text
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    deadline = datetime.fromisoformat(end)
    with pytest.raises(EvidenceError):
        MemoryArchiveService(h.service.memory, clock=FrozenClock(deadline - timedelta(microseconds=1))).archive(
            "alice", "self", row["id"], expected_revision=row["revision"], operation_id="range-before-end"
        )
    archive_at = max(deadline, datetime.fromisoformat(row["said_at"]))
    archived = MemoryArchiveService(h.service.memory, clock=FrozenClock(archive_at)).archive(
        "alice", "self", row["id"], expected_revision=row["revision"], operation_id="range-at-end"
    )
    assert archived["write_status"] == "archived"
    h.finish()


def test_legacy_pending_proposal_recomputes_range_from_actual_source(tool_repo):
    h = setup(tool_repo, "我这周复诊了", parser=ModuleTimeRangeParser())
    pending, _, _ = h.write("event", sensitivity="health")
    proposal = tool_repo.get("alice", "proposal", pending.receipt["id"])
    payload = {
        key: value
        for key, value in proposal.items()
        if key not in {"fact_metadata", "categories", "id", "owner", "revision", "created_at", "updated_at"}
    }
    legacy = tool_repo.put("alice", "proposal", proposal["id"], payload, expected_revision=proposal["revision"])
    assert "fact_metadata" not in legacy
    action = h.service.memory.receive("alice", content="请保存这条记忆", source_id="legacy-range-accept")
    receipt = MemoryProposalService(h.service.memory).accept(
        "alice",
        "self",
        legacy["id"],
        expected_revision=legacy["revision"],
        message_id=action["id"],
        remember_category=False,
        operation_id="legacy-range-accept",
    )
    row = tool_repo.get("alice", "fact", receipt["fact_id"])
    assert row["precision"] == "range" and row["event_at"] == "2026-10-11T16:00:00+00:00"
    assert row["event_end"] == "2026-10-18T16:00:00+00:00" and row["original_expression"] == "这周"
    assert not h.service.memory.repo.assert_scope("alice")["settings"].get("auto_save_categories")
    h.finish()
