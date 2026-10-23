"""Contradiction suggestions never overwrite an unclassified old statement."""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .contracts import MemoryFact
from .dedup import normalized

_NEGATION = re.compile(r"不再|不喜欢|不爱|不想|不愿|不吃|不喝|不能|不需要|从不|没有|没在|不是|讨厌|喜欢|喜爱")
_OPPOSITE = (("喜欢", "讨厌"), ("能", "不能"), ("已经", "还没"), ("离职", "入职"))


@dataclass(frozen=True)
class PossibleConflict:
    old_id: str
    new_id: str
    similarity: float
    proposal: str = field(repr=False)


def possible_conflicts(incoming: MemoryFact, facts: tuple[MemoryFact, ...]) -> tuple[PossibleConflict, ...]:
    return tuple(candidate for old in facts if (candidate := _candidate(old, incoming)) is not None)


def _candidate(old: MemoryFact, new: MemoryFact) -> PossibleConflict | None:
    if (old.owner_id, old.subject_id, old.origin) != (new.owner_id, new.subject_id, "user"):
        return None
    if old.id == new.id or old.status != "active" or old.valid_to is not None:
        return None
    if old.slot is not None or new.slot is not None:
        return None
    before, after = normalized(old.text), normalized(new.text)
    if before == after:
        return None
    stripped_old, stripped_new = _NEGATION.sub("", before), _NEGATION.sub("", after)
    score = SequenceMatcher(None, stripped_old, stripped_new).ratio()
    negative = bool(re.search(r"不|没|讨厌", before)) != bool(re.search(r"不|没|讨厌", after))
    opposite = any((a in before and b in after) or (b in before and a in after) for a, b in _OPPOSITE)
    if score < 0.70 or not (negative or opposite):
        return None
    return PossibleConflict(old.id, new.id, score, f"以前你说“{old.text}”，现在说“{new.text}”，以哪个为准？")
