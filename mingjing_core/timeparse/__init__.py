"""Unified offline time interpretation; all callers supply an aware reference instant."""

from .contracts import AbsolutizedText, ParseContext, TimeCandidate, TimeRangeResult
from .parser import absolutize, parse_time_range

__all__ = ["AbsolutizedText", "ParseContext", "TimeCandidate", "TimeRangeResult", "absolutize", "parse_time_range"]
