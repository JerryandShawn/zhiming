"""Review-only work products retain source versions; none is a tool call or save receipt."""

from dataclasses import dataclass, field
from datetime import datetime

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, SourceAnchor
from mingjing_core.memory2.event_time_extended_v2 import ExtendedEventCandidate
from mingjing_core.memory2.reflection import ReflectionProposal

from .effects import ReflectionEffects
from .schedule_contracts import ReflectionIntent
from .validation import ReflectionError, booleans, identities, instant, integer, opaque, typed_tuple


@dataclass(frozen=True)
class BoundExcerpt:
    source_id: str
    source_revision: int
    role: str
    at: datetime
    anchor: SourceAnchor = field(repr=False)

    def __post_init__(self) -> None:
        opaque(self.source_id)
        integer(self.source_revision, 1)
        if (
            type(self.role) is not str
            or self.role not in {"user", "assistant"}
            or not isinstance(self.anchor, SourceAnchor)
        ):
            raise ReflectionError("excerpt_role_or_anchor_invalid")
        if (self.source_id, self.source_revision) != (self.anchor.source_id, self.anchor.revision):
            raise ReflectionError("excerpt_anchor_binding_invalid")
        object.__setattr__(self, "at", instant(self.at))


@dataclass(frozen=True)
class ExtractiveSummary:
    id: str
    scope: MemoryScope
    thread_id: str
    kind: str
    snapshot_revision: int
    source_epoch: int
    excerpts: tuple[BoundExcerpt, ...] = field(repr=False)
    method: str = "extractive_quotes_only"
    mood: str = "not_inferred"
    conclusion: str = "not_inferred"

    def __post_init__(self) -> None:
        opaque(self.id, self.thread_id)
        if not isinstance(self.scope, MemoryScope) or self.kind not in {
            "episode_candidate",
            "thread_summary_candidate",
        }:
            raise ReflectionError("summary_scope_or_kind_invalid")
        integer(self.snapshot_revision)
        integer(self.source_epoch)
        object.__setattr__(self, "excerpts", typed_tuple(self.excerpts, BoundExcerpt))
        if self.method != "extractive_quotes_only" or self.mood != "not_inferred" or self.conclusion != "not_inferred":
            raise ReflectionError("extractive_summary_cannot_infer_emotion_or_conclusion")


@dataclass(frozen=True)
class FactCandidate:
    fact: MemoryFact = field(repr=False)
    policy_action: str
    requires_confirmation: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.fact, MemoryFact) or self.fact.origin != "user":
            raise ReflectionError("missing_user_fact_required")
        if type(self.policy_action) is not str or self.policy_action not in {"save", "proposal", "profile_confirm"}:
            raise ReflectionError("candidate_policy_action_invalid")
        booleans(self.requires_confirmation)
        if self.requires_confirmation != (self.policy_action != "save"):
            raise ReflectionError("candidate_confirmation_mismatch")


@dataclass(frozen=True)
class DuplicateCandidate:
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    expected_revisions: tuple[tuple[str, int], ...]
    action: str = "review_merge_only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "fact_ids", identities(self.fact_ids, minimum=2))
        object.__setattr__(self, "source_ids", identities(self.source_ids))
        revisions = typed_tuple(self.expected_revisions, tuple)
        for entry in revisions:
            if len(entry) != 2:
                raise ReflectionError("candidate_revision_invalid")
            opaque(entry[0])
            integer(entry[1], 1)
        if {entry[0] for entry in revisions} != set(self.fact_ids) or len(revisions) != len(self.fact_ids):
            raise ReflectionError("candidate_revision_manifest_mismatch")
        object.__setattr__(self, "expected_revisions", revisions)
        if self.action != "review_merge_only":
            raise ReflectionError("candidate_action_invalid")


@dataclass(frozen=True)
class KnowledgeGap:
    id: str
    reason: str
    question: str = field(repr=False)
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    priority: int = 3
    action: str = "review_gap_only"

    def __post_init__(self) -> None:
        opaque(self.id, self.reason)
        integer(self.priority, 1)
        if self.priority > 5 or self.action != "review_gap_only":
            raise ReflectionError("gap_priority_or_action_invalid")
        if type(self.question) is not str or not self.question.strip() or len(self.question) > 10000:
            raise ReflectionError("gap_question_invalid")
        object.__setattr__(self, "fact_ids", identities(self.fact_ids))
        object.__setattr__(self, "source_ids", identities(self.source_ids))


@dataclass(frozen=True)
class ExistingGap:
    scope: MemoryScope
    id: str
    revision: int
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    priority: int = 3
    mentions: int = 0
    blocking: bool = False
    status: str = "open"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("gap_scope_required")
        opaque(self.id)
        integer(self.revision, 1)
        integer(self.priority, 1)
        integer(self.mentions)
        booleans(self.blocking)
        if (
            self.priority > 5
            or type(self.status) is not str
            or self.status not in {"open", "asked", "answered", "dismissed"}
        ):
            raise ReflectionError("gap_priority_or_status_invalid")
        for key in ("fact_ids", "source_ids"):
            values = typed_tuple(getattr(self, key), str)
            opaque(*values)
            if len(set(values)) != len(values):
                raise ReflectionError("duplicate_gap_source")
            object.__setattr__(self, key, values)


@dataclass(frozen=True)
class GapPriorityCandidate:
    gap_id: str
    expected_revision: int
    priority: int
    source_ids: tuple[str, ...]
    method: str = "explicit_blocking_and_mentions_v1"

    def __post_init__(self) -> None:
        opaque(self.gap_id)
        integer(self.expected_revision, 1)
        integer(self.priority, 1)
        if self.priority > 5 or self.method != "explicit_blocking_and_mentions_v1":
            raise ReflectionError("gap_priority_invalid")
        object.__setattr__(self, "source_ids", identities(self.source_ids))


@dataclass(frozen=True)
class ArchiveCandidate:
    fact_id: str
    expected_revision: int
    source_ids: tuple[str, ...]
    deadline: datetime
    action: str = "review_archive_only"

    def __post_init__(self) -> None:
        opaque(self.fact_id)
        integer(self.expected_revision, 1)
        object.__setattr__(self, "source_ids", identities(self.source_ids))
        object.__setattr__(self, "deadline", instant(self.deadline))
        if self.action != "review_archive_only":
            raise ReflectionError("candidate_action_invalid")


@dataclass(frozen=True)
class FollowupCandidate:
    fact_id: str
    expected_revision: int
    source_ids: tuple[str, ...]
    event_at: datetime
    event_end: datetime | None
    action: str = "host_schedule_review_required"

    def __post_init__(self) -> None:
        opaque(self.fact_id)
        integer(self.expected_revision, 1)
        object.__setattr__(self, "source_ids", identities(self.source_ids))
        object.__setattr__(self, "event_at", instant(self.event_at))
        if self.event_end is not None:
            object.__setattr__(self, "event_end", instant(self.event_end))
            if self.event_end < self.event_at:
                raise ReflectionError("candidate_event_range_invalid")
        if self.action != "host_schedule_review_required":
            raise ReflectionError("candidate_action_invalid")


@dataclass(frozen=True)
class WorkOmission:
    id: str
    reason: str

    def __post_init__(self) -> None:
        opaque(self.id, self.reason)


@dataclass(frozen=True)
class InvalidationCandidate:
    scope: MemoryScope
    thread_id: str
    snapshot_revision: int
    source_epoch: int
    source_ids: tuple[str, ...]
    action: str = "host_invalidation_review_only"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("invalidation_scope_required")
        opaque(self.thread_id)
        integer(self.snapshot_revision)
        integer(self.source_epoch)
        object.__setattr__(self, "source_ids", identities(self.source_ids, minimum=0))
        if self.action != "host_invalidation_review_only":
            raise ReflectionError("candidate_action_invalid")


@dataclass(frozen=True)
class ReflectionWorkPlan:
    intent: ReflectionIntent
    evaluated_at: datetime
    status: str
    reason: str
    fingerprint: str
    episodes: tuple[ExtractiveSummary, ...] = field(default=(), repr=False)
    rolling_summary: ExtractiveSummary | None = field(default=None, repr=False)
    fact_candidates: tuple[FactCandidate, ...] = field(default=(), repr=False)
    duplicates: tuple[DuplicateCandidate, ...] = ()
    gaps: tuple[KnowledgeGap, ...] = field(default=(), repr=False)
    gap_priorities: tuple[GapPriorityCandidate, ...] = ()
    date_repairs: tuple[ExtendedEventCandidate, ...] = field(default=(), repr=False)
    profile_proposals: tuple[ReflectionProposal, ...] = field(default=(), repr=False)
    archive_candidates: tuple[ArchiveCandidate, ...] = ()
    followup_candidates: tuple[FollowupCandidate, ...] = ()
    omissions: tuple[WorkOmission, ...] = ()
    warnings: tuple[str, ...] = ()
    invalidations: tuple[InvalidationCandidate, ...] = ()
    effects: ReflectionEffects = ReflectionEffects()

    def __post_init__(self) -> None:
        from .validation import sha

        if (
            not isinstance(self.intent, ReflectionIntent)
            or type(self.status) is not str
            or self.status not in {"planned", "blocked"}
        ):
            raise ReflectionError("work_intent_or_status_invalid")
        sha(self.fingerprint)
        object.__setattr__(self, "evaluated_at", instant(self.evaluated_at))
        types = (
            ("episodes", ExtractiveSummary),
            ("fact_candidates", FactCandidate),
            ("duplicates", DuplicateCandidate),
            ("gaps", KnowledgeGap),
            ("gap_priorities", GapPriorityCandidate),
            ("date_repairs", ExtendedEventCandidate),
            ("profile_proposals", ReflectionProposal),
            ("archive_candidates", ArchiveCandidate),
            ("followup_candidates", FollowupCandidate),
            ("omissions", WorkOmission),
            ("warnings", str),
            ("invalidations", InvalidationCandidate),
        )
        for name, kind in types:
            object.__setattr__(self, name, typed_tuple(getattr(self, name), kind))
        if not isinstance(self.effects, ReflectionEffects):
            raise ReflectionError("effects_must_be_zero")
        if self.rolling_summary is not None and not isinstance(self.rolling_summary, ExtractiveSummary):
            raise ReflectionError("rolling_summary_invalid")
        if self.status == "blocked" and (
            self.rolling_summary is not None or any(getattr(self, name) for name, _ in types if name != "warnings")
        ):
            raise ReflectionError("blocked_work_cannot_carry_candidates")
