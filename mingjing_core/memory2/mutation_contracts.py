"""Full before/after snapshots support replay and conditional field-wise undo."""

from dataclasses import dataclass, field
from datetime import datetime

from .contracts import Confirmation, MemoryFact, MemoryScope, MemorySettings, MemorySnapshot
from .validation import frozen_tuple, require_int, require_text, unique


@dataclass(frozen=True)
class FactChange:
    id: str
    before: MemoryFact | None = field(repr=False)
    after: MemoryFact | None = field(repr=False)

    def __post_init__(self) -> None:
        require_text(self.id)
        for fact in (self.before, self.after):
            if fact is not None and (not isinstance(fact, MemoryFact) or fact.id != self.id):
                raise ValueError("memory_change_invalid")


@dataclass(frozen=True)
class MutationPlan:
    operation_id: str
    scope: MemoryScope
    expected_revision: int
    source_epoch: int
    changes: tuple[FactChange, ...] = field(default=(), repr=False)
    write_status: str = "saved"
    summary: str = field(default="", repr=False)
    question_key: str | None = None
    fingerprint: str = ""
    incoming: MemoryFact | None = field(default=None, repr=False)
    settings: MemorySettings = MemorySettings()
    confirmation: Confirmation | None = field(default=None, repr=False)
    model_hint: tuple[str, ...] = ()
    evaluated_at: datetime | None = None
    policy_action: str = "metadata"

    def __post_init__(self) -> None:
        require_text(self.operation_id, self.write_status, self.policy_action)
        require_int(self.expected_revision)
        require_int(self.source_epoch)
        if not isinstance(self.scope, MemoryScope) or not isinstance(self.settings, MemorySettings):
            raise ValueError("memory_plan_invalid")
        if self.incoming is not None and not isinstance(self.incoming, MemoryFact):
            raise ValueError("memory_plan_invalid")
        if self.confirmation is not None and not isinstance(self.confirmation, Confirmation):
            raise ValueError("memory_plan_invalid")
        object.__setattr__(self, "changes", frozen_tuple(self.changes, FactChange))
        object.__setattr__(self, "model_hint", frozen_tuple(self.model_hint, str))
        unique(change.id for change in self.changes)


@dataclass(frozen=True)
class MutationOutcome:
    snapshot: MemorySnapshot = field(repr=False)
    write_status: str
    summary: str = field(default="", repr=False)
    fact_ids: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    replayed: bool = False


class MutationConflict(ValueError):
    """Concurrent writes and incompatible replays are domain conflicts."""
