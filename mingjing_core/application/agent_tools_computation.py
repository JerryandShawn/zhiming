"""Absolute-date arithmetic only; relative language stays in the U4 integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from mingjing_core.agent.tools.computation_parameters import DateCalc
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.date_calculation import calculate
from mingjing_core.domain.contracts import EvidenceError


def date_calc(
    arguments: dict[str, Any], *, ref_time: datetime | None = None, timezone: str = "Asia/Shanghai"
) -> ToolResult:
    args = DateCalc.model_validate(arguments)
    if args.op is not None:
        try:
            data = calculate(args, ref_time, timezone)
        except (OverflowError, ValueError):
            raise EvidenceError("日期参数无效或超出支持范围") from None
        return ToolResult(ok=True, data=data, summary="算了一下日期")
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
        summary="算了一下日期",
    )
