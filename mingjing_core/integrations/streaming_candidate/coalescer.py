"""Pure text batching; a new revision discards unreviewed buffered draft text."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from mingjing_core.timekit.clock import Clock

from .event_models import EventDraft, RunScope
from .stream_clock import StreamStateError, observe, utc


@dataclass(frozen=True)
class DeltaPolicy:
    max_chars: int = 40
    max_delay_ms: int = 150

    def __post_init__(self) -> None:
        if type(self.max_chars) is not int or not 1 <= self.max_chars <= 200_000:
            raise StreamStateError("文本合并字数无效")
        if type(self.max_delay_ms) is not int or not 1 <= self.max_delay_ms <= 60_000:
            raise StreamStateError("文本合并时长无效")


DEFAULT_POLICY = DeltaPolicy()


@dataclass(frozen=True)
class DeltaBuffer:
    scope: RunScope
    text: str = field(default="", repr=False)
    opened_at: datetime | None = None
    last_observed_at: datetime | None = None
    generation: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RunScope) or not isinstance(self.text, str) or len(self.text) > 200_000:
            raise StreamStateError("文本缓冲格式无效")
        if type(self.generation) is not int or self.generation < 0:
            raise StreamStateError("文本修订版本无效")
        for name in ("opened_at", "last_observed_at"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, utc(getattr(self, name)))
        if bool(self.text) != (self.opened_at is not None):
            raise StreamStateError("文本缓冲起始时刻无效")
        if self.opened_at is not None and self.last_observed_at is not None and self.opened_at > self.last_observed_at:
            raise StreamStateError("文本缓冲时刻顺序无效")


@dataclass(frozen=True)
class DeltaEmission:
    state: DeltaBuffer
    drafts: tuple[EventDraft, ...] = ()


def _drafts(text: str) -> tuple[EventDraft, ...]:
    return tuple(
        EventDraft("text_delta", {"text": text[index : index + 200_000]}) for index in range(0, len(text), 200_000)
    )


def flush_delta(buffer: DeltaBuffer, *, clock: Clock) -> DeltaEmission:
    stamp = observe(clock, buffer.last_observed_at or buffer.opened_at)
    return _flush_at(buffer, stamp)


def _flush_at(buffer: DeltaBuffer, stamp: datetime) -> DeltaEmission:
    return DeltaEmission(replace(buffer, text="", opened_at=None, last_observed_at=stamp), _drafts(buffer.text))


def poll_delta(buffer: DeltaBuffer, *, clock: Clock, policy: DeltaPolicy = DEFAULT_POLICY) -> DeltaEmission:
    stamp = observe(clock, buffer.last_observed_at or buffer.opened_at)
    if buffer.opened_at is not None and stamp - buffer.opened_at >= timedelta(milliseconds=policy.max_delay_ms):
        return _flush_at(buffer, stamp)
    return DeltaEmission(replace(buffer, last_observed_at=stamp))


def feed_delta(
    buffer: DeltaBuffer, chunk: str, *, generation: int, clock: Clock, policy: DeltaPolicy = DEFAULT_POLICY
) -> DeltaEmission:
    if type(generation) is not int or generation != buffer.generation:
        raise StreamStateError("文本修订已变化，请停止旧写入者")
    if not isinstance(chunk, str) or len(chunk) > 200_000:
        raise StreamStateError("文本片段格式无效")
    elapsed = poll_delta(buffer, clock=clock, policy=policy)
    stamp = elapsed.state.last_observed_at
    combined = elapsed.state.text + chunk
    state = replace(elapsed.state, text="", opened_at=None)
    if len(combined) >= policy.max_chars:
        return DeltaEmission(state, (*elapsed.drafts, *_drafts(combined)))
    state = replace(state, text=combined, opened_at=elapsed.state.opened_at or (stamp if combined else None))
    return DeltaEmission(state, elapsed.drafts)


def replace_text(
    buffer: DeltaBuffer,
    text: str,
    *,
    reason: str,
    revision_id: str | None = None,
    clock: Clock,
) -> DeltaEmission:
    stamp = observe(clock, buffer.last_observed_at or buffer.opened_at)
    payload = {"text": text, "reason": reason}
    if revision_id is not None:
        payload["revision_id"] = revision_id
    draft = EventDraft("text_reset", payload)
    state = replace(buffer, text="", opened_at=None, last_observed_at=stamp, generation=buffer.generation + 1)
    return DeltaEmission(state, (draft,))
