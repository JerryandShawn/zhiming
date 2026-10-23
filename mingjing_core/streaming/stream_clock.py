"""State transitions observe an injected clock in UTC, independent of the host timezone."""

from datetime import UTC, datetime

from mingjing_core.timekit.clock import Clock


class StreamStateError(ValueError):
    """A stale writer or incompatible transition must not publish new text."""


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StreamStateError("流式时间需要带时区")
    return value.astimezone(UTC)


def observe(clock: Clock, previous: datetime | None) -> datetime:
    now = utc(clock.now())
    if previous is not None and now < utc(previous):
        raise StreamStateError("流式观察时刻不能倒退")
    return now
