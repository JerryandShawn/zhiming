"""K1 subscription time is explicit and independent of proactive quiet-hour shifting."""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mingjing_core.application.followups_contracts import FollowupScope

from .recurrence_contracts import NextTriggerResult, RecurrenceRule, aware


@dataclass(frozen=True)
class BriefSubscription:
    scope: FollowupScope
    enabled: bool = True
    local_time: time = time(7)
    time_zone: str = "Asia/Shanghai"
    revision: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.scope, FollowupScope) or type(self.enabled) is not bool:
            raise ValueError("晨报订阅归属或开关无效")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("晨报订阅版本无效")
        if not isinstance(self.local_time, time) or self.local_time.tzinfo is not None:
            raise ValueError("晨报时刻必须为用户当地时刻")
        try:
            ZoneInfo(self.time_zone)
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            raise ValueError("晨报时区无效") from None


def next_brief(subscription: BriefSubscription, after: datetime, *, inclusive: bool = False) -> NextTriggerResult:
    from .recurrence import next_trigger

    after = aware(after)
    if not subscription.enabled:
        return NextTriggerResult(None, reason="brief_not_subscribed")
    rule = RecurrenceRule("daily", subscription.local_time, time_zone=subscription.time_zone)
    return next_trigger(rule, after, inclusive=inclusive)
