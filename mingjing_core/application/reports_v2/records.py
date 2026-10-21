"""Current authorized user records only; source failure never becomes a claim about reality."""

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from mingjing_core.application.briefing_v2.authorization import state_reason
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.organize.spaces import DEFAULT_SPACES

from .citations import CitationRegistry
from .contracts import ReportError, ReportOmission, ReportPeriod, ReportRecord, ReportSection
from .periods import includes_instant

AREAS = {row.id: row.name for row in DEFAULT_SPACES}
LABELS = {"fact": "已记录的用户事实", "arrangement": "用户安排（结果未确认）", "followup": "跟进线索（不执行提醒）"}


def record_sections(
    records: Sequence[ReportRecord],
    *,
    scope: FollowupScope,
    period: ReportPeriod,
    now: datetime,
    registry: CitationRegistry,
) -> tuple[tuple[ReportSection, ...], tuple[ReportOmission, ...], tuple[str, ...]]:
    if not isinstance(records, (tuple, list)) or any(not isinstance(row, ReportRecord) for row in records):
        raise ReportError("report_records_required")
    seen, groups, omissions, used = {}, {}, [], []
    for row in records:
        if row.scope != scope:
            raise ReportError("record_scope_mismatch")
        if row.id in seen and seen[row.id] != row:
            raise ReportError("record_identity_content_changed")
        seen[row.id] = row
    for row in sorted(seen.values(), key=lambda item: (item.at or item.said_at, item.id)):
        reason = _reason(row, scope, period, now)
        if reason is not None:
            omissions.append(ReportOmission(row.id, reason))
            continue
        at = row.at or row.said_at
        when = at.astimezone(ZoneInfo(period.timezone)).strftime("%m-%d %H:%M")
        prefix = "记录于" if row.at is None else "原定于" if row.category != "fact" else "事件时间"
        line = registry.line(f"{prefix}{when}：{row.text}", row.basis, event_at=row.at, said_at=row.said_at)
        groups.setdefault((row.category, row.area_id), []).append(line)
        used.append(row.id)
    sections = tuple(
        ReportSection(
            f"{kind}_{area or 'unorganized'}",
            LABELS[kind] + " · " + AREAS.get(area, "待整理"),
            kind,
            tuple(groups[(kind, area)]),
            area,
        )
        for kind in LABELS
        for area in (*AREAS, None)
        if (kind, area) in groups
    )
    return sections, tuple(omissions), tuple(used)


def _reason(row: ReportRecord, scope: FollowupScope, period: ReportPeriod, now: datetime) -> str | None:
    if row.origin != "user":
        return "assistant_claim_is_not_user_fact"
    if row.status != "active":
        return "record_not_active"
    if row.said_at > now:
        return "source_message_in_future"
    if row.valid_from is not None and row.valid_from > now:
        return "record_not_yet_valid"
    if row.valid_to is not None and row.valid_to <= now:
        return "record_expired"
    reason = state_reason(row.basis, row.source_states, scope)
    if reason is not None:
        return reason
    if not includes_instant(period, row.at or row.said_at, row.end):
        return "outside_report_period"
    if row.category == "fact" and row.at is not None and row.at > now:
        return "future_event_not_observed"
    return None
