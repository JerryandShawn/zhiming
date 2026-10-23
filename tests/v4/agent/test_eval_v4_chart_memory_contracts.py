"""Date precision and sensitive family statements cannot be inferred from gold."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mingjing_core.application.agent_tools_dates import event_metadata
from mingjing_core.application.agent_tools_policy import sensitivity
from mingjing_core.application.time_range_parser import ModuleTimeRangeParser


@pytest.mark.parametrize("kind", ["goal", "preference", "constraint", "background"])
def test_vague_non_event_preserves_said_at_without_fabricating_event_date(kind):
    class NoDateClaim:
        def resolve(self, *args, **kwargs):
            raise AssertionError("non-event without claimed date must not demand calendar precision")

    service = SimpleNamespace(timezone=lambda ctx: "Asia/Shanghai", relative_parser=NoDateClaim())
    metadata, pending = event_metadata(
        service, {"kind": kind, "quote": "我最近在准备考研"}, None, {"at": "2026-10-17T10:30:00+08:00"}
    )
    assert pending is None and "event_at" not in metadata
    assert datetime.fromisoformat(metadata["said_at"]) == datetime(2026, 10, 17, 2, 30, tzinfo=UTC)


def test_event_with_vague_time_still_requires_confirmation():
    service = SimpleNamespace(timezone=lambda ctx: "Asia/Shanghai", relative_parser=ModuleTimeRangeParser())
    metadata, pending = event_metadata(
        service, {"kind": "event", "quote": "我最近参加面试"}, None, {"at": "2026-10-17T10:30:00+08:00"}
    )
    assert pending["code"] == "date_ambiguous" and "event_at" not in metadata


@pytest.mark.parametrize(
    "text", ["我妈今年血压一直很高", "妈妈今年血压很高", "我父亲最近确诊了高血压", "我的朋友一直用药"]
)
def test_explicit_family_or_friend_health_stays_third_party_even_if_model_reports_normal(text):
    assert sensitivity(text, text, 0, len(text), "normal") == "third_party"


@pytest.mark.parametrize("text", ["我本人今年血压一直很高", "我今年血压一直很高", "同事说我今年血压偏高"])
def test_own_health_is_not_relabelled_third_party(text):
    assert sensitivity(text, text, 0, len(text), "normal") == "health"
