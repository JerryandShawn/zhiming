"""Deterministic report content only. No subscription, notification or Outbox permission is created."""

from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.briefing_v2.calendar import calendar_section
from mingjing_core.application.briefing_v2.contracts import BasisRef, CalendarSnapshot
from mingjing_core.application.followups_contracts import FollowupScope, aware
from mingjing_core.timekit.clock import Clock

from .citations import CitationRegistry
from .contracts import (
    DailyTransitInput,
    PeriodReport,
    ReportCitation,
    ReportCoverage,
    ReportError,
    ReportPeriod,
    ReportRecord,
    ReportSection,
    SyntheticSymbolicInput,
)
from .manifest import validate_batch_manifest
from .periods import period_for
from .records import record_sections
from .symbolic import symbolic_sections

LABELS = {"weekly": "周报", "monthly": "月报", "quarterly": "季报"}


def compose_period_report(
    *,
    scope: FollowupScope,
    kind: str,
    day: date,
    clock: Clock,
    timezone: str = "Asia/Shanghai",
    records: Sequence[ReportRecord] = (),
    transits: Sequence[DailyTransitInput] = (),
    profile_revision: int | None = None,
    synthetic_symbolic: Sequence[SyntheticSymbolicInput] = (),
    calendar: CalendarSnapshot | None = None,
) -> PeriodReport:
    if not isinstance(scope, FollowupScope):
        raise ReportError("report_scope_required")
    validate_batch_manifest(records, transits, synthetic_symbolic, scope)
    period, now, registry = period_for(kind, day, timezone), aware(clock.now()), CitationRegistry()
    basis = _period_basis(scope, period)
    header = registry.line(
        f"{LABELS[kind]}；期间 {period.start_day.isoformat()} 至 {period.end_day.isoformat()}（含末日），"
        f"按 {timezone} 日界；当前周期口径，不自动改成上一周期。",
        (basis,),
    )
    sections = [ReportSection("period", "报告期间", "calendar", (header,))]
    current, warnings = _calendar(calendar, scope, period, now, registry)
    if current is not None:
        sections.append(current)
    real, omissions, used = record_sections(records, scope=scope, period=period, now=now, registry=registry)
    sections.extend(real)
    symbolic, days, synthetic_days, notices = symbolic_sections(
        transits,
        synthetic_symbolic,
        scope=scope,
        period=period,
        profile_revision=profile_revision,
        registry=registry,
    )
    sections.extend(symbolic)
    if not used:
        warnings = (*warnings, "no_current_authorized_records_supplied")
    sections.append(_limits(registry, basis, bool(used)))
    citations = registry.all()
    claims = tuple(dict.fromkeys(row.basis.claim_id for row in citations if row.basis.claim_id is not None))
    key = _request_key(scope, period, sections, citations)
    return PeriodReport(
        scope,
        period,
        now,
        tuple(sections),
        citations,
        used,
        claims,
        omissions,
        tuple(dict.fromkeys((*warnings, *notices))),
        ReportCoverage(period.days, days, synthetic_days),
        key,
    )


def _period_basis(scope: FollowupScope, period: ReportPeriod) -> BasisRef:
    digest = fingerprint([period.kind, period.key, period.timezone, period.start.isoformat(), period.end.isoformat()])
    return BasisRef(
        "t1", "report-period:" + period.key, 1, scope.owner_id, scope.subject_id, digest, "report-period:" + digest, "/"
    )


def _calendar(
    snapshot: CalendarSnapshot | None,
    scope: FollowupScope,
    period: ReportPeriod,
    now: datetime,
    registry: CitationRegistry,
) -> tuple[ReportSection | None, tuple[str, ...]]:
    if snapshot is None:
        return None, ("send_time_calendar_not_supplied",)
    if not isinstance(snapshot, CalendarSnapshot) or snapshot.scope != scope:
        raise ReportError("calendar_scope_mismatch")
    if snapshot.timezone != period.timezone or snapshot.day != now.astimezone(ZoneInfo(period.timezone)).date():
        return None, ("calendar_snapshot_day_or_timezone_mismatch",)
    if not timedelta() <= now - snapshot.observed_at <= timedelta(minutes=15):
        return None, ("send_time_calendar_snapshot_not_fresh",)
    source = calendar_section(snapshot)
    return ReportSection(
        "now_calendar",
        "编排此刻历法（不是整周期历法）",
        "calendar",
        tuple(registry.line(row.text, row.basis) for row in source.lines),
    ), ()


def _limits(registry: CitationRegistry, basis: BasisRef, has_records: bool) -> ReportSection:
    lines = [
        "本报告只整理已提供且当前仍有效的来源；事实、安排和象征说明分开。安排不代表已经完成。",
        "流日资料仅描述列明日期北京时间12:00瞬间，不外推整周期趋势；未提供流月或流季权威计算。",
        "过期或退役资料未自动复活；这是内容投影，不执行提醒或授权发送。",
    ]
    if not has_records:
        lines.append("未提供当前授权记录，不等于这个期间没有发生事情。")
    return ReportSection("limits", "资料与使用边界", "limits", tuple(registry.line(value, (basis,)) for value in lines))


def _request_key(
    scope: FollowupScope,
    period: ReportPeriod,
    sections: list[ReportSection],
    citations: tuple[ReportCitation, ...],
) -> str:
    content = [
        [
            row.id,
            row.title,
            row.category,
            row.area_id,
            [
                [
                    line.text,
                    [item.local_alias for item in line.citations],
                    line.event_at.isoformat() if line.event_at is not None else None,
                    line.said_at.isoformat() if line.said_at is not None else None,
                ]
                for line in row.lines
            ],
        ]
        for row in sections
    ]
    projection = [
        scope.owner_id,
        scope.subject_id,
        period.kind,
        period.key,
        period.timezone,
        content,
        [asdict(row) for row in citations],
    ]
    return "period-report:" + fingerprint(projection)
