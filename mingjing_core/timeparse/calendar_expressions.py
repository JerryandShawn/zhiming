"""Calendar expression dispatch; every dated lookup delegates to the injected read-only P2 port."""

from .calendar_holidays import parse_holiday, parse_newyear
from .calendar_lunar import parse_ambiguous_lunar, parse_lunar
from .calendar_lunar_cycles import parse_lunar_cycle
from .calendar_port import CalendarPort, P2CalendarPort
from .calendar_terms import parse_term
from .contracts import ParseContext, TimeRangeResult


def parse_calendar(text: str, ctx: ParseContext, calendar: CalendarPort | None = None) -> TimeRangeResult | None:
    port = calendar if calendar is not None else P2CalendarPort()
    parsers = (parse_lunar_cycle, parse_lunar, parse_holiday, parse_newyear, parse_term, parse_ambiguous_lunar)
    for parser in parsers:
        result = parser(text, ctx, port)
        if result is not None:
            return result
    return None
