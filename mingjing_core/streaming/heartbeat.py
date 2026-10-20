"""Heartbeat comments do not enter event storage or consume a sequence number."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from mingjing_core.timekit.clock import Clock

from .stream_clock import StreamStateError, observe, utc


@dataclass(frozen=True)
class HeartbeatState:
    last_sent_at: datetime
    last_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "last_sent_at", utc(self.last_sent_at))
        if self.last_observed_at is not None:
            object.__setattr__(self, "last_observed_at", utc(self.last_observed_at))
            if self.last_observed_at < self.last_sent_at:
                raise StreamStateError("心跳观察时刻无效")


@dataclass(frozen=True)
class HeartbeatTick:
    state: HeartbeatState
    comment: str | None


def heartbeat_tick(state: HeartbeatState, *, clock: Clock) -> HeartbeatTick:
    stamp = observe(clock, state.last_observed_at or state.last_sent_at)
    if stamp - state.last_sent_at >= timedelta(seconds=15):
        return HeartbeatTick(HeartbeatState(stamp, stamp), ": ping\n\n")
    return HeartbeatTick(HeartbeatState(state.last_sent_at, stamp), None)
