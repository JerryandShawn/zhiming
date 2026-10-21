"""Exact class identities actually nested in frozen reflection projection call sites."""

from dataclasses import fields
from types import MappingProxyType

from mingjing_core.application.reflection_v3.effects import ReflectionEffects
from mingjing_core.application.reflection_v3.schedule_contracts import ProcessedSource, ReflectionIntent
from mingjing_core.application.reflection_v3.work_contracts import (
    ArchiveCandidate,
    BoundExcerpt,
    DuplicateCandidate,
    ExtractiveSummary,
    FactCandidate,
    FollowupCandidate,
    GapPriorityCandidate,
    InvalidationCandidate,
    KnowledgeGap,
    ReflectionWorkPlan,
    WorkOmission,
)
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, SourceAnchor
from mingjing_core.memory2.event_time_extended_v2 import ExtendedEventCandidate
from mingjing_core.memory2.reflection import ReflectionProposal
from mingjing_core.timeparse.contracts import AbsolutizedText, TimeCandidate, TimeRangeResult

SUPPORTED_TYPES = (
    MemoryScope,
    MemoryFact,
    SourceAnchor,
    ReflectionProposal,
    ExtendedEventCandidate,
    TimeCandidate,
    TimeRangeResult,
    AbsolutizedText,
    ReflectionEffects,
    ProcessedSource,
    ReflectionIntent,
    BoundExcerpt,
    ExtractiveSummary,
    FactCandidate,
    DuplicateCandidate,
    KnowledgeGap,
    GapPriorityCandidate,
    ArchiveCandidate,
    FollowupCandidate,
    WorkOmission,
    InvalidationCandidate,
    ReflectionWorkPlan,
)

# Integer identity keys never invoke an input metaclass's __hash__/__eq__. Values retain class references.
# Only field names are cached. Source text, permissions, clock values and results never are.
FIELD_NAMES = MappingProxyType(
    {id(kind): (kind, tuple(item.name for item in fields(kind))) for kind in SUPPORTED_TYPES}
)
