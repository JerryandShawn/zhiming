"""Absolute-date arithmetic only; relative language stays in the U4 integration."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mingjing_core.agent.tools.computation_parameters import DateCalc
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import EvidenceError


def date_calc(arguments: dict[str, Any]) -> ToolResult:
    args = DateCalc.model_validate(arguments)
    start = date.fromisoformat(args.start_date)
    try:
        end = start + timedelta(days=args.days) if args.operation == "add_days" else date.fromisoformat(args.end_date)
    except (OverflowError, ValueError):
        raise EvidenceError("日期计算超出支持范围") from None
    return ToolResult(
        ok=True,
        data={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_weekday": start.isoweekday(),
            "end_weekday": end.isoweekday(),
            "days": (end - start).days,
            "difference_basis": "end_minus_start",
        },
        summary="绝对日期运算已完成",
    )
