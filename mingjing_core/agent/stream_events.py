"""Internal model-step lifecycle; public event fields remain frozen v1."""

from typing import Protocol

from .journal import JournalStep


class ModelTextStream(Protocol):
    def begin(self, step: JournalStep) -> None: ...

    def push(self, text: str) -> None: ...

    def finish(self, step: JournalStep, *, succeeded: bool) -> None: ...
