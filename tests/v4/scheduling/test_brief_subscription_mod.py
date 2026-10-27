"""Default 07:00 is a subscription input; it must not inherit the old 08:30 quiet shift."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.scheduling.brief_schedule import BriefSubscription, next_brief

SCOPE = FollowupScope("owner", "self")


def test_beijing_default_is_seven_and_same_instant_on_tokyo_host():
    after = datetime(2026, 10, 20, 22, tzinfo=UTC)
    first = next_brief(BriefSubscription(SCOPE), after)
    second = next_brief(BriefSubscription(SCOPE), after.astimezone(ZoneInfo("Asia/Tokyo")))
    assert first.at == second.at == datetime(2026, 10, 20, 23, tzinfo=UTC)


def test_user_time_and_disabled_subscription():
    after = datetime(2026, 10, 20, 22, tzinfo=UTC)
    assert next_brief(BriefSubscription(SCOPE, local_time=time(6, 30)), after).at.minute == 30
    assert next_brief(BriefSubscription(SCOPE, enabled=False), after).at is None


@pytest.mark.parametrize("enabled", ["false", 1, None])
def test_untyped_subscription_flag_rejected(enabled):
    with pytest.raises(ValueError):
        BriefSubscription(SCOPE, enabled=enabled)
