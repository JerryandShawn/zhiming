"""Profile expiry follows the event's recorded timezone after owner settings change."""

from datetime import datetime
from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_profile_reflection import ProfileReflectionService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import FrozenClock

from .test_memory2_slots_pg import fact
from .test_memory2_slots_pg import slots_repo as base_slots_repo


@pytest.fixture(name="tool_repo")
def profile_zone_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return base_slots_repo.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize(
    "zone,now,allowed",
    [
        ("America/Los_Angeles", "2026-10-18T06:59:59+00:00", True),
        ("America/Los_Angeles", "2026-10-18T07:00:00+00:00", False),
        ("Asia/Tokyo", "2026-10-17T15:30:00+00:00", False),
    ],
)
def test_profile_event_expiry_uses_original_zone_at_its_boundary(
    tool_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
    zone: str,
    now: str,
    allowed: bool,
) -> None:
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(datetime.fromisoformat(now)))
    assert tool_repo.assert_scope("alice")["settings"].get("timezone", "Asia/Shanghai") == "Asia/Shanghai"
    row = fact(
        tool_repo,
        "我2026年10月17日参加合成活动",
        "2026-10-16T10:00:00+08:00",
        requested_kind="event",
        event_at="2026-10-17",
        owner_timezone=zone,
    )
    service = ProfileReflectionService(V4FactMemory(tool_repo))
    if allowed:
        result = service.prepare("alice", "self", [row["id"]])
        assert result["fact_versions"] == {row["id"]: row["revision"]}
    else:
        with pytest.raises(EvidenceError, match="过期"):
            service.prepare("alice", "self", [row["id"]])
