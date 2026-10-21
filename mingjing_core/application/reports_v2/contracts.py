"""Immutable report inputs and outputs. Host snapshots are consistency inputs, not database authentication."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from mingjing_core.application.briefing_v2.contracts import BasisRef, BriefSourceState, refs, text
from mingjing_core.application.followups_contracts import FollowupScope, aware
from mingjing_core.organize.spaces import DEFAULT_SPACES
from mingjing_core.streaming.json_values import freeze_json, json_object

T = TypeVar("T")


class ReportError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("报告资料暂不可用，请核对归属、期间与来源")


@dataclass(frozen=True)
class ReportPeriod:
    kind: str
    key: str
    timezone: str
    start_day: date
    end_day: date
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        from mingjing_core.domain.report_schedules import report_period, report_period_bounds

        if type(self.kind) is not str or self.kind not in {"weekly", "monthly", "quarterly"}:
            raise ReportError("period_kind_invalid")
        if type(self.start_day) is not date or type(self.end_day) is not date:
            raise ReportError("period_dates_required")
        bounds = report_period_bounds(self.kind, self.start_day)
        if self.key != report_period(self.kind, self.start_day) or bounds != {
            "start": self.start_day.isoformat(),
            "end": self.end_day.isoformat(),
        }:
            raise ReportError("period_does_not_match_v3_bounds")
        zone = ZoneInfo(self.timezone)
        for name in ("start", "end"):
            object.__setattr__(self, name, aware(getattr(self, name)))
        expected_start = aware(datetime.combine(self.start_day, time(), zone))
        expected_end = aware(datetime.combine(self.end_day + timedelta(days=1), time(), zone))
        if self.start != expected_start or self.end != expected_end:
            raise ReportError("period_instants_invalid")

    @property
    def days(self) -> int:
        return (self.end_day - self.start_day).days + 1


def _states(value: object) -> tuple[BriefSourceState, ...]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(row, BriefSourceState) for row in value):
        raise ReportError("current_source_states_invalid")
    if len({row.source_id for row in value}) != len(value):
        raise ReportError("duplicate_current_source_states")
    return tuple(value)


@dataclass(frozen=True)
class ReportRecord:
    scope: FollowupScope
    id: str
    category: str
    text: str = field(repr=False)
    said_at: datetime
    basis: tuple[BasisRef, ...]
    source_states: tuple[BriefSourceState, ...] = field(default=(), repr=False)
    at: datetime | None = None
    end: datetime | None = None
    area_id: str | None = None
    status: str = "active"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    origin: str = "user"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, FollowupScope):
            raise ReportError("record_scope_required")
        text(self.id)
        if type(self.text) is not str or not self.text.strip() or len(self.text) > 4000:
            raise ReportError("record_text_invalid")
        if type(self.category) is not str or self.category not in {"fact", "arrangement", "followup"}:
            raise ReportError("record_category_invalid")
        if (
            type(self.status) is not str
            or type(self.origin) is not str
            or (
                self.status not in {"active", "retired", "archived", "deleted"}
                or self.origin not in {"user", "assistant_claim"}
            )
        ):
            raise ReportError("record_status_or_origin_invalid")
        if self.area_id is not None and self.area_id not in {row.id for row in DEFAULT_SPACES}:
            raise ReportError("record_area_invalid")
        object.__setattr__(self, "basis", refs(self.basis))
        object.__setattr__(self, "source_states", _states(self.source_states))
        object.__setattr__(self, "said_at", aware(self.said_at))
        for key in ("at", "end", "valid_from", "valid_to"):
            if getattr(self, key) is not None:
                object.__setattr__(self, key, aware(getattr(self, key)))
        if self.end is not None and (self.at is None or self.end <= self.at):
            raise ReportError("record_time_range_invalid")
        if self.valid_from is not None and self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ReportError("record_validity_range_invalid")


@dataclass(frozen=True)
class DailyTransitInput:
    day: date
    payload: Mapping[str, Any] = field(repr=False)
    current_state: BriefSourceState | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.day) is not date:
            raise ReportError("transit_day_required")
        if self.current_state is not None and not isinstance(self.current_state, BriefSourceState):
            raise ReportError("transit_current_state_invalid")
        object.__setattr__(self, "payload", freeze_json(json_object(self.payload)))


@dataclass(frozen=True)
class SyntheticSymbolicInput:
    scope: FollowupScope
    id: str
    day: date
    text: str = field(repr=False)
    convention: str
    basis: tuple[BasisRef, ...]
    source_states: tuple[BriefSourceState, ...] = field(default=(), repr=False)
    synthetic: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.scope, FollowupScope) or type(self.day) is not date or self.synthetic is not True:
            raise ReportError("synthetic_symbolic_boundary_invalid")
        text(self.id)
        text(self.convention, maximum=120)
        if type(self.text) is not str or not self.text.strip() or len(self.text) > 2000:
            raise ReportError("synthetic_symbolic_text_invalid")
        object.__setattr__(self, "basis", refs(self.basis))
        object.__setattr__(self, "source_states", _states(self.source_states))
        if any(not ref.source_id.startswith("synthetic-") or ref.claim_id is not None for ref in self.basis):
            raise ReportError("synthetic_source_must_not_impersonate_chart_claim")


@dataclass(frozen=True)
class ReportCitation:
    local_alias: str
    source_alias: str
    basis: BasisRef

    def __post_init__(self) -> None:
        if not isinstance(self.basis, BasisRef) or self.source_alias != self.basis.alias:
            raise ReportError("citation_origin_binding_invalid")
        if type(self.local_alias) is not str or re.fullmatch(r"[a-z][1-9][0-9]*", self.local_alias) is None:
            raise ReportError("citation_local_alias_invalid")


@dataclass(frozen=True)
class ReportLine:
    text: str = field(repr=False)
    citations: tuple[ReportCitation, ...]
    event_at: datetime | None = None
    said_at: datetime | None = None

    def __post_init__(self) -> None:
        if type(self.text) is not str or not self.text.strip() or len(self.text) > 5000:
            raise ReportError("report_line_invalid")
        object.__setattr__(self, "citations", _tuple(self.citations, ReportCitation, empty=False))
        for name in ("event_at", "said_at"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, aware(getattr(self, name)))


@dataclass(frozen=True)
class ReportSection:
    id: str
    title: str
    category: str
    lines: tuple[ReportLine, ...] = field(repr=False)
    area_id: str | None = None

    def __post_init__(self) -> None:
        text(self.id)
        text(self.title, maximum=200)
        if self.category not in {
            "calendar",
            "fact",
            "arrangement",
            "followup",
            "symbolic",
            "synthetic_symbolic",
            "limits",
        }:
            raise ReportError("section_category_invalid")
        object.__setattr__(self, "lines", _tuple(self.lines, ReportLine, empty=False))


@dataclass(frozen=True)
class ReportOmission:
    record_id: str
    reason: str


@dataclass(frozen=True)
class ReportEffects:
    model_calls: int = 0
    writes: int = 0
    notifications: int = 0
    scheduler_mutations: int = 0

    def __post_init__(self) -> None:
        if any(type(getattr(self, key)) is not int or getattr(self, key) != 0 for key in self.__dataclass_fields__):
            raise ReportError("report_effects_must_be_zero")


@dataclass(frozen=True)
class ReportCoverage:
    period_days: int
    rendered_snapshot_days: tuple[date, ...]
    synthetic_days: tuple[date, ...]

    def __post_init__(self) -> None:
        if type(self.period_days) is not int or not 1 <= self.period_days <= 366:
            raise ReportError("coverage_days_invalid")
        for key in ("rendered_snapshot_days", "synthetic_days"):
            value = _tuple(getattr(self, key), date)
            if any(type(day) is not date for day in value) or len(set(value)) != len(value):
                raise ReportError("coverage_date_invalid")
            object.__setattr__(self, key, value)


@dataclass(frozen=True)
class PeriodReport:
    scope: FollowupScope
    period: ReportPeriod
    generated_at: datetime
    sections: tuple[ReportSection, ...] = field(repr=False)
    citations: tuple[ReportCitation, ...]
    used_record_ids: tuple[str, ...]
    used_claim_ids: tuple[str, ...]
    omissions: tuple[ReportOmission, ...]
    warnings: tuple[str, ...]
    coverage: ReportCoverage
    request_key: str
    effects: ReportEffects = ReportEffects()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, FollowupScope) or not isinstance(self.period, ReportPeriod):
            raise ReportError("result_scope_or_period_invalid")
        object.__setattr__(self, "generated_at", aware(self.generated_at))
        for key, cls in (("sections", ReportSection), ("citations", ReportCitation), ("omissions", ReportOmission)):
            object.__setattr__(self, key, _tuple(getattr(self, key), cls))
        for key in ("used_record_ids", "used_claim_ids", "warnings"):
            value = _tuple(getattr(self, key), str)
            if len(set(value)) != len(value):
                raise ReportError("duplicate_result_identity")
            object.__setattr__(self, key, value)
        if not isinstance(self.coverage, ReportCoverage) or self.coverage.period_days != self.period.days:
            raise ReportError("result_coverage_mismatch")
        if not isinstance(self.effects, ReportEffects):
            raise ReportError("result_effects_invalid")
        for citation in self.citations:
            if (citation.basis.owner_id, citation.basis.subject_id) != (self.scope.owner_id, self.scope.subject_id):
                raise ReportError("result_citation_scope_mismatch")


def _tuple(value: object, cls: type[T], *, empty: bool = True) -> tuple[T, ...]:
    if (
        not isinstance(value, (tuple, list))
        or (not empty and not value)
        or any(not isinstance(row, cls) for row in value)
    ):
        raise ReportError("typed_report_sequence_required")
    return tuple(value)
