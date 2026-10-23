"""Opt-in local period report projections; original schedules, worker and daily briefing are untouched."""

from mingjing_core.application.briefing_v2.contracts import BasisRef, BriefSourceState

from .compose import compose_period_report
from .contracts import (
    DailyTransitInput,
    PeriodReport,
    ReportCitation,
    ReportCoverage,
    ReportEffects,
    ReportError,
    ReportLine,
    ReportOmission,
    ReportPeriod,
    ReportRecord,
    ReportSection,
    SyntheticSymbolicInput,
)
from .periods import period_for

__all__ = [
    "BasisRef",
    "BriefSourceState",
    "DailyTransitInput",
    "PeriodReport",
    "ReportCitation",
    "ReportCoverage",
    "ReportEffects",
    "ReportError",
    "ReportLine",
    "ReportOmission",
    "ReportPeriod",
    "ReportRecord",
    "ReportSection",
    "SyntheticSymbolicInput",
    "compose_period_report",
    "period_for",
]
