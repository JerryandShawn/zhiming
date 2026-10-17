"""Replay supplied model actions without consulting expected assertions."""

from copy import deepcopy
from typing import Any


class ScriptedProvider:
    """A strict, deterministic action queue for framework tests and v4."""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = {item["turn"]: deepcopy(item["model"]) for item in script}
        if len(self._script) != len(script):
            raise ValueError("scripted turns must be unique")
        self._consumed: set[int] = set()

    def replay(self, turn: int) -> list[dict[str, Any]]:
        if turn in self._consumed:
            raise ValueError("scripted turn already consumed")
        if turn not in self._script:
            raise ValueError("missing scripted turn")
        self._consumed.add(turn)
        return deepcopy(self._script[turn])

    def generate(self, *, turn: int, **_: Any) -> dict[str, Any]:
        return {
            "actions": self.replay(turn),
            "model": "scripted-v1",
            "latency_seconds": 0.0,
        }
