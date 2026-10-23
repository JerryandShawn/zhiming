"""Offline evaluation uses the same real U4 injection as the production AgentRuntime."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_runtime import AgentRuntime


class EvaluationRuntime(AgentRuntime):
    def __init__(self, *args: Any, offline: bool = True, **kwargs: Any) -> None:
        if offline is not True:
            raise ValueError("v4脚本评测只接受离线运行")
        # No parser built from scripts or expected event_at values is admitted.
        # AgentRuntime's actual U4 parser is the only default implementation.
        super().__init__(*args, offline=True, **kwargs)
