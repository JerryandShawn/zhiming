"""Inject the offline U4 contract substitute without reimplementing the loop."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.agent_tools_contracts import DateResolution


class DeclaredDateParser:
    """Z6 substitute: explicit script answers, not a relative-language parser."""

    def __init__(self, scripts: list[dict[str, Any]]) -> None:
        self.rows = []
        for step in scripts:
            for action in step["model"]:
                call = action.get("tool_call", {})
                args = call.get("arguments", {})
                if call.get("name") == "memory_write" and args.get("event_at"):
                    self.rows.append((args["quote"], args["event_at"]))

    def resolve(self, text: str, *, said_at: datetime, timezone: str) -> DateResolution:
        exact = [day for quote, day in self.rows if text == quote]
        if len(set(exact)) == 1:
            return DateResolution("resolved", event_at=exact[0], expression=text)
        return DateResolution("not_date")


class EvaluationRuntime(AgentRuntime):
    def __init__(self, *args: Any, parser: DeclaredDateParser, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.parser = parser

    def _cycle(self, *args: Any, **kwargs: Any) -> Any:
        cycle = super()._cycle(*args, **kwargs)
        cycle.registry.service.relative_parser = self.parser
        return cycle
