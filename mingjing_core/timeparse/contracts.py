"""Aware, half-open ranges; no host timezone, clock reads, persistence, or model access."""

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

TimeKind = Literal["point", "range", "recurring"]
WEEKDAYS = "一二三四五六日"


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间解析需要带时区的参考时间")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ParseContext:
    ref_time: datetime
    tz: str = "Asia/Shanghai"
    text: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_time", aware(self.ref_time))
        ZoneInfo(self.tz)
        if not isinstance(self.text, str):
            raise ValueError("待解析内容需要是文字")

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def local_ref(self) -> datetime:
        return self.ref_time.astimezone(self.zone)

    @property
    def local_date(self) -> date:
        return self.local_ref.date()


@dataclass(frozen=True)
class TimeCandidate:
    start: datetime | None
    end: datetime | None
    granularity: str = "day"
    kind: TimeKind = "point"
    confidence: float = 0.9
    normalized_text: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if self.start is not None:
            object.__setattr__(self, "start", aware(self.start))
        if self.end is not None:
            object.__setattr__(self, "end", aware(self.end))
        if self.kind not in {"point", "range", "recurring"} or not 0 <= self.confidence <= 1:
            raise ValueError("时间候选格式无效")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("时间范围结束不能早于开始")


@dataclass(frozen=True)
class TimeRangeResult(TimeCandidate):
    candidates: tuple[TimeCandidate, ...] = ()
    needs_clarification: bool = False
    original_text: str = field(default="", repr=False)
    matched_text: str = field(default="", repr=False)
    span: tuple[int, int] | None = None
    recurrence: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        def convert(value: object) -> object:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(item) for item in value]
            return value

        return convert(asdict(self))


@dataclass(frozen=True)
class AbsolutizedText:
    original_text: str = field(repr=False)
    text: str = field(repr=False)
    result: TimeRangeResult
    replaced: bool

    @property
    def normalized_text(self) -> str:
        return self.text


def local_midnight(day: date, ctx: ParseContext) -> datetime:
    return datetime.combine(day, time(), ctx.zone)


def absolute_day(day: date) -> str:
    return f"{day.isoformat()}（周{WEEKDAYS[day.weekday()]}）"


def make_result(
    ctx: ParseContext,
    *,
    start: date | datetime | None,
    end: date | datetime | None,
    matched_text: str,
    granularity: str = "day",
    kind: TimeKind = "point",
    confidence: float = 0.95,
    normalized_text: str | None = None,
    candidates: tuple[TimeCandidate, ...] = (),
    needs_clarification: bool = False,
    recurrence: str | None = None,
    reason: str | None = None,
) -> TimeRangeResult:
    beginning = local_midnight(start, ctx) if type(start) is date else start
    ending = local_midnight(end, ctx) if type(end) is date else end
    label = (
        normalized_text
        if normalized_text is not None
        else absolute_day(beginning.astimezone(ctx.zone).date())
        if beginning
        else ""
    )
    index = ctx.text.find(matched_text) if matched_text else -1
    return TimeRangeResult(
        beginning,
        ending,
        granularity,
        kind,
        confidence,
        label,
        "",
        candidates,
        needs_clarification,
        ctx.text,
        matched_text,
        (index, index + len(matched_text)) if index >= 0 else None,
        recurrence,
        reason,
    )


def bind_text(result: TimeRangeResult, ctx: ParseContext, matched_text: str) -> TimeRangeResult:
    index = ctx.text.find(matched_text)
    return replace(
        result,
        original_text=ctx.text,
        matched_text=matched_text,
        span=(index, index + len(matched_text)) if index >= 0 else None,
    )
