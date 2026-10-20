"""Label-free message projection and topic scoring for the final sealed evaluator."""

from collections import defaultdict
from collections.abc import Callable

from mingjing_core.organize.contracts import Message
from mingjing_core.organize.v2.metrics import classification_metrics
from mingjing_core.organize.v2.scoped import OrganizeScope
from mingjing_core.organize.v2.topics import cluster_messages

UNTHREADED = "__synthetic_unthreaded__"


def message_from_record(record: dict) -> Message:
    """Explicit projection excludes every expected_* field and context-group hint."""
    thread = record.get("thread_id") or UNTHREADED
    return Message(
        id=record["id"],
        role=record.get("role", "user"),
        content=record["content"],
        at_ms=record.get("at_ms", 0),
        owner_id=record["owner_id"],
        subject_id=record["subject_id"],
        revision=record.get("revision", 1),
        status=record.get("status", "active"),
        incognito=record.get("incognito", False),
        thread_id=thread,
        retention_scope=record.get("retention_scope", "persistent"),
    )


def scope_for(message: Message) -> OrganizeScope:
    return OrganizeScope(message.owner_id, message.subject_id, message.thread_id)


def scoped_topic_gold(record: dict) -> str | None:
    value = record.get("expected_topic")
    if value is None:
        return None
    if type(value) is not str or not value:
        raise ValueError("topic_gold_label_invalid")
    scope = scope_for(message_from_record(record))
    return repr((scope.owner_id, scope.subject_id, scope.thread_id, value))


def topic_metrics(
    records: list[dict],
    predictions: dict,
    *,
    similarity_threshold: float = 0.4,
    clusterer: Callable = cluster_messages,
) -> dict:
    groups = defaultdict(list)
    for record in records:
        message = message_from_record(record)
        groups[scope_for(message)].append(message)
    expected_keys = {(scope, message.id) for scope, messages in groups.items() for message in messages}
    if len(expected_keys) != len(records):
        raise ValueError("topic_duplicate_scoped_message")
    assigned = {}
    for scope, messages in groups.items():
        local = {message.id: predictions[(scope, message.id)] for message in messages}
        topics = clusterer(
            tuple(messages),
            local,
            scope=scope,
            similarity_threshold=similarity_threshold,
        )
        for topic in topics:
            for identity in topic.message_ids:
                key = scope, identity
                if key in assigned or identity not in local:
                    raise ValueError("topic_assignment_scope_or_identity_invalid")
                assigned[key] = repr((scope.owner_id, scope.subject_id, scope.thread_id, topic.id))
    if set(assigned) != expected_keys:
        raise ValueError("topic_assignment_coverage_incomplete")
    # Gold is first inspected after every label-free clustering call is complete.
    gold = [scoped_topic_gold(record) for record in records]
    predicted = []
    for record in records:
        identity = scope_for(message_from_record(record)), record["id"]
        predicted.append(assigned[identity] if predictions[identity].area_id is not None else None)
    scores = classification_metrics(gold, predicted)
    return {
        "topic_ari_clear_all": scores["ari_clear_all"],
        "topic_ari_clear_assigned": scores["ari_clear_assigned"],
        "topic_ari_all": scores["ari_all"],
        "topic_ari_assigned": scores["ari_assigned"],
        "topic_clear_count": scores["clear_count"],
        "topic_total": scores["total"],
        "topic_assigned_count": scores["assigned"],
        "topic_ari_status": "character_ngram_clustering_after_area_predictions_without_gold",
        "topic_ari_policy": "clear_* includes explicit gold-topic; all_* also includes unknown gold",
    }
