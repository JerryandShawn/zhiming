"""Offline deterministic brief sections; no scheduler, notification, profile lookup, or model call."""

from .authorization import subscription_basis
from .calendar import calendar_snapshot
from .compose import compose_briefing
from .contracts import (
    BasisRef,
    BriefEffects,
    BriefingError,
    BriefingResult,
    BriefItem,
    BriefLine,
    BriefOmission,
    BriefSection,
    BriefSourceState,
    CalendarSnapshot,
)

__all__ = [
    "BasisRef",
    "BriefEffects",
    "BriefItem",
    "BriefLine",
    "BriefOmission",
    "BriefSection",
    "BriefSourceState",
    "BriefingError",
    "BriefingResult",
    "CalendarSnapshot",
    "calendar_snapshot",
    "compose_briefing",
    "subscription_basis",
]
