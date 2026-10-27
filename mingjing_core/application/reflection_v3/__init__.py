"""Pure background planning. No queue, model, storage or notification operation is implemented."""

from .effects import ReflectionEffects
from .profile_contracts import AboutMeSection, AboutMeView, ProfileDocument, ProfileEntry, ProfileLine
from .profile_renderer import render_about_me
from .schedule import schedule_reflection
from .schedule_contracts import (
    BackgroundPermit,
    ProcessedSource,
    ReflectionIntent,
    ReflectionOperation,
    ScheduleDecision,
    ThreadState,
)
from .validation import ReflectionError
from .work import plan_reflection_work
from .work_contracts import ExistingGap, ReflectionWorkPlan

__all__ = [
    "BackgroundPermit",
    "ProcessedSource",
    "ReflectionError",
    "ReflectionIntent",
    "ReflectionOperation",
    "ScheduleDecision",
    "ThreadState",
    "schedule_reflection",
    "AboutMeSection",
    "AboutMeView",
    "ProfileDocument",
    "ProfileEntry",
    "ProfileLine",
    "render_about_me",
    "plan_reflection_work",
    "ExistingGap",
    "ReflectionWorkPlan",
    "ReflectionEffects",
]
