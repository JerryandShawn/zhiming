"""The small target boundary shared by fake, v3 and future v4 adapters."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TurnResult:
    """Observable output, with call metadata separated from answer text."""

    text: str = ""
    tools_called: list[str] = field(default_factory=list)
    receipts: list[dict[str, Any]] = field(default_factory=list)
    db: dict[str, Any] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    model_calls: int = 0
    elapsed_seconds: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Target(Protocol):
    """A target owns only its isolated state and must release it on close."""

    def reset(self, seed: dict[str, Any]) -> None: ...

    def send(self, turn: dict[str, Any]) -> TurnResult: ...

    def inspect_db(self) -> dict[str, Any]: ...

    def close(self) -> None: ...
