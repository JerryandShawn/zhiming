"""Trusted adapters to the module parser; source instants and owner zones stay explicit."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.application.agent_tools_contracts import DateResolution
from mingjing_core.domain.time_ranges import TimeRangeResult
from mingjing_core.timeparse import parse_time_range


class ModuleTimeRangeParser:
    """Serve the range contract and conservative single-event memory contract."""

    def parse_time_range(
        self,
        text: str,
        ref_time: datetime,
        tz: str = "Asia/Shanghai",
        calendar: Any = None,
    ) -> TimeRangeResult:
        result = parse_time_range(text, ref_time, tz, calendar)
        data = result.as_dict()
        return TimeRangeResult.model_validate(
            {key: data[key] for key in TimeRangeResult.model_fields}
        )

    def resolve(self, text: str, *, said_at: datetime, timezone: str) -> DateResolution:
        result = parse_time_range(text, said_at, timezone)
        if not result.matched_text and not result.needs_clarification:
            return DateResolution("not_date")
        if (
            result.needs_clarification
            or result.confidence < 0.8
            or result.start is None
            or result.kind != "point"
            or not result.matched_text
        ):
            return DateResolution(
                "needs_confirmation",
                candidates=tuple(
                    candidate.normalized_text for candidate in result.candidates
                ),
                reason=result.reason or "single_event_date_required",
            )
        event_at = (
            result.start.astimezone(ZoneInfo(timezone)).date().isoformat()
            if result.granularity == "day"
            else result.start.isoformat()
        )
        return DateResolution("resolved", event_at, result.matched_text)
