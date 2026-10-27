"""Single-day chart descriptions cannot be silently promoted to a weekly/monthly/quarterly forecast."""

from collections.abc import Sequence
from datetime import UTC, date, datetime

from mingjing_core.application.briefing_v2.authorization import state_reason, transit_state_reason
from mingjing_core.application.briefing_v2.transit import transit_section
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.streaming.json_values import thaw_json

from .citations import CitationRegistry
from .contracts import DailyTransitInput, ReportError, ReportPeriod, ReportSection, SyntheticSymbolicInput


def symbolic_sections(
    transits: Sequence[DailyTransitInput],
    synthetic: Sequence[SyntheticSymbolicInput],
    *,
    scope: FollowupScope,
    period: ReportPeriod,
    profile_revision: int | None,
    registry: CitationRegistry,
) -> tuple[tuple[ReportSection, ...], tuple[date, ...], tuple[date, ...], tuple[str, ...]]:
    _inputs(transits, synthetic, scope)
    sections, days, synthetic_days, warnings, seen = [], [], [], [], {}
    for row in sorted(transits, key=lambda item: item.day):
        if row.day in seen:
            if seen[row.day] != row:
                raise ReportError("same_day_transit_changed")
            continue
        seen[row.day] = row
        if not period.start_day <= row.day <= period.end_day:
            warnings.append("transit_outside_report_period")
            continue
        payload = thaw_json(row.payload)
        reason = transit_state_reason(payload, row.current_state, scope, profile_revision)
        if reason:
            warnings.append(reason)
            continue
        try:
            section, notices = transit_section(payload, scope=scope, day=row.day, profile_revision=profile_revision)
            warnings.extend(notices)
        except (ValueError, TypeError, KeyError):
            warnings.append("transit_invalid_or_unavailable")
            continue
        if section is not None:
            at = datetime.fromisoformat(payload["data"]["snapshot_at"]).astimezone(UTC)
            lines = tuple(
                registry.line(row.day.isoformat() + "；" + line.text, line.basis, event_at=at) for line in section.lines
            )
            sections.append(
                ReportSection(
                    "symbolic_" + row.day.isoformat(), "单日象征结构 · " + row.day.isoformat(), "symbolic", lines
                )
            )
            days.append(row.day)
    extra, synthetic_days, notices = _synthetic(synthetic, scope, period, registry)
    sections.extend(extra)
    warnings.extend(notices)
    if len(set(days)) < period.days:
        warnings.append("period_symbolic_coverage_incomplete_no_extrapolation")
    if synthetic_days:
        warnings.append("synthetic_symbolic_is_not_chart_evidence")
    return tuple(sections), tuple(sorted(set(days))), tuple(sorted(set(synthetic_days))), tuple(dict.fromkeys(warnings))


def _synthetic(
    synthetic: Sequence[SyntheticSymbolicInput],
    scope: FollowupScope,
    period: ReportPeriod,
    registry: CitationRegistry,
) -> tuple[list[ReportSection], list[date], list[str]]:
    sections, synthetic_days, warnings, seen = [], [], [], {}
    for row in synthetic:
        if row.id in seen:
            if seen[row.id] != row:
                raise ReportError("synthetic_identity_content_changed")
            continue
        seen[row.id] = row
        if period.start_day <= row.day <= period.end_day:
            reason = state_reason(row.basis, row.source_states, scope)
            if reason is None:
                value = f"{row.day.isoformat()}；合成接口替身（{row.convention}），不代表实际排盘：{row.text}"
                sections.append(
                    ReportSection(
                        "synthetic_" + row.id, "合成象征素材", "synthetic_symbolic", (registry.line(value, row.basis),)
                    )
                )
                synthetic_days.append(row.day)
            else:
                warnings.append(reason)
    return sections, synthetic_days, warnings


def _inputs(
    transits: Sequence[DailyTransitInput], synthetic: Sequence[SyntheticSymbolicInput], scope: FollowupScope
) -> None:
    if not isinstance(transits, (list, tuple)) or any(not isinstance(row, DailyTransitInput) for row in transits):
        raise ReportError("daily_transit_inputs_required")
    if not isinstance(synthetic, (list, tuple)) or any(
        not isinstance(row, SyntheticSymbolicInput) for row in synthetic
    ):
        raise ReportError("synthetic_symbolic_inputs_required")
    if any(row.scope != scope for row in synthetic):
        raise ReportError("synthetic_symbolic_scope_mismatch")
    for row in transits:
        identity = row.payload.get("scope")
        if isinstance(identity, dict) or hasattr(identity, "get"):
            actual = (identity.get("owner_user_id"), identity.get("subject_id"))
            if all(type(value) is str for value in actual) and actual != (scope.owner_id, scope.subject_id):
                raise ReportError("transit_scope_mismatch")
