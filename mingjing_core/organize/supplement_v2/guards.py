"""Reuse current user/source/anchor policy instead of treating classification as authorization."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, SourceAnchor, utc
from mingjing_core.memory2.guards import authorize_fact
from mingjing_core.memory2.sensitivity import Sensitivity, classify_sensitivity
from mingjing_core.timekit.clock import Clock

from .contracts import EntityRecord, ReviewApproval, SupplementConflict, SupplementSnapshot, TopicRecord


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def anchor_values(anchors: tuple[SourceAnchor, ...]) -> list[tuple[str, int, int, int, str]]:
    return [(item.source_id, item.revision, item.start, item.end, item.quote_fingerprint) for item in anchors]


def evidence_fingerprint(entity: EntityRecord) -> str:
    return digest(
        (
            entity.id,
            entity.scope.owner_id,
            entity.scope.subject_id,
            entity.kind,
            entity.revision,
            hashlib.sha256(entity.text.encode()).hexdigest(),
            entity.said_at.isoformat(),
            anchor_values(entity.anchors),
            entity.active,
            entity.current,
            entity.revoked,
            entity.incognito,
            entity.origin,
            entity.sensitive_categories,
        )
    )


def topic_fingerprint(topic: TopicRecord) -> str:
    return digest(
        (
            topic.id,
            topic.scope.owner_id,
            topic.scope.subject_id,
            topic.revision,
            topic.last_at.isoformat(),
            hashlib.sha256(topic.title.encode()).hexdigest(),
            anchor_values(topic.anchors),
            topic.active,
            topic.current,
            topic.revoked,
            topic.incognito,
        )
    )


def require_scope(snapshot: SupplementSnapshot, scope: MemoryScope) -> None:
    if not isinstance(snapshot, SupplementSnapshot) or not isinstance(scope, MemoryScope) or snapshot.scope != scope:
        raise SupplementConflict("scope_mismatch")


def authorize_entity(entity: EntityRecord, snapshot: SupplementSnapshot, scope: MemoryScope) -> None:
    require_scope(snapshot, scope)
    if entity.scope != scope or not entity.active or not entity.current or entity.revoked or entity.incognito:
        raise SupplementConflict("entity_unavailable")
    surrogate = MemoryFact(
        entity.id,
        scope.owner_id,
        scope.subject_id,
        "note" if entity.origin == "assistant_claim" else "background",
        entity.text,
        tuple(dict.fromkeys(item.source_id for item in entity.anchors)),
        entity.said_at,
        entity.said_at,
        anchors=entity.anchors,
        origin=entity.origin,
    )
    authorize_fact(surrogate, MemorySnapshot(scope, sources=snapshot.sources), scope)


def authorize_topic(topic: TopicRecord, snapshot: SupplementSnapshot, scope: MemoryScope) -> None:
    require_scope(snapshot, scope)
    if not topic.anchors:
        raise SupplementConflict("topic_source_required")
    primary = next((source for source in snapshot.sources if source.id == topic.anchors[0].source_id), None)
    if primary is None:
        raise SupplementConflict("topic_source_required")
    surrogate = EntityRecord(
        topic.id,
        topic.scope,
        "case",
        topic.title or topic.anchors[0].quote,
        primary.at,
        topic.anchors,
        revision=topic.revision,
        active=topic.active,
        current=topic.current,
        revoked=topic.revoked,
        incognito=topic.incognito,
    )
    authorize_entity(surrogate, snapshot, scope)
    if any(source.at > topic.last_at for source in snapshot.sources if source.id in surrogate_source_ids(surrogate)):
        raise SupplementConflict("topic_last_at_precedes_source")


def surrogate_source_ids(entity: EntityRecord) -> frozenset[str]:
    return frozenset(item.source_id for item in entity.anchors)


def entity_sensitivity(entity: EntityRecord) -> Sensitivity:
    text = "\n".join((entity.text, *(anchor.quote for anchor in entity.anchors)))
    return classify_sensitivity(text, model_hint=entity.sensitive_categories)


def require_approval(approval: ReviewApproval, scope: MemoryScope, fingerprint: str) -> None:
    if (
        not isinstance(approval, ReviewApproval)
        or approval.scope != scope
        or approval.fingerprint != fingerprint
        or approval.decision != "approved"
        or approval.actor != "user"
    ):
        raise SupplementConflict("review_approval_mismatch")


def entity_from_fact(
    fact: MemoryFact,
    snapshot: MemorySnapshot,
    *,
    labels: Mapping[str, object] | None = None,
    clock: Clock | None = None,
) -> EntityRecord:
    authorize_fact(fact, snapshot, snapshot.scope)
    if clock is None and (fact.valid_to is not None or fact.valid_from > fact.said_at):
        raise SupplementConflict("fact_validity_clock_required")
    now = utc(clock.now()) if clock is not None else fact.said_at
    current = (
        fact.superseded_by is None
        and fact.valid_from <= now
        and (fact.valid_to is None or now < fact.valid_to)
        and fact.said_at <= now
        and (clock is None or fact.recorded_at <= now)
    )
    entity = EntityRecord(
        fact.id,
        snapshot.scope,
        "note" if fact.origin == "assistant_claim" else "fact",
        fact.text,
        fact.said_at,
        fact.anchors,
        fact.revision,
        labels or {},
        origin=fact.origin,
        current=current,
    )
    return replace(entity, active=fact.status == "active" and fact.source_valid)
