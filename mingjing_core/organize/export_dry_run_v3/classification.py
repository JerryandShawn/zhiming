"""Frozen Q5 sees only authorized user text; answers inherit labels, never user assertions."""

from collections import defaultdict

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize.contracts import Message, Topic
from mingjing_core.organize.v2.classifier import LocalClassifier
from mingjing_core.organize.v2.contracts import ClassificationContext, Prediction
from mingjing_core.organize.v2.scoped import OrganizeScope
from mingjing_core.organize.v2.topics import cluster_messages

from .contracts import ExportMessage, ParsedExport

GAP_MS = 6 * 60 * 60 * 1000


def classify_export(
    parsed: ParsedExport, scope: MemoryScope
) -> tuple[tuple[Topic, ...], dict[str, Prediction], dict[str, str], tuple[str, ...]]:
    engine, predictions, parents, previous = LocalClassifier(), {}, {}, {}
    messages = {message.id: message for message in parsed.messages}
    ordered = sorted(parsed.payload["messages"], key=lambda item: (item["at_ms"], item["id"]))
    waiting = []
    for raw in ordered:
        message = messages.get(raw["id"])
        thread = raw["thread_id"]
        if message is None:
            if raw["role"] == "user":
                previous.pop(thread, None)
            continue
        prior = previous.get(thread)
        if prior is not None and message.at_ms - prior.at_ms > GAP_MS:
            prior = None
        if message.role == "assistant":
            if prior is None or prior.at_ms >= message.at_ms or predictions[prior.id].waiting:
                waiting.append(message.id)
            else:
                parents[message.id] = prior.id
            continue
        context = None
        if prior is not None:
            predicted = predictions[prior.id]
            context = ClassificationContext(predicted.area_id, predicted.confidence, previous_text=prior.text)
        predictions[message.id] = engine.classify(message.text, context)
        previous[thread] = message
        if predictions[message.id].waiting:
            waiting.append(message.id)
    topics = _cluster(parsed.messages, predictions, scope)
    return topics, predictions, parents, tuple(sorted(waiting))


def _cluster(
    messages: tuple[ExportMessage, ...], predictions: dict[str, Prediction], scope: MemoryScope
) -> tuple[Topic, ...]:
    grouped = defaultdict(list)
    for message in messages:
        if message.role == "user" and not predictions[message.id].waiting:
            grouped[message.thread_id].append(message)
    topics = []
    for thread, values in sorted(grouped.items()):
        session = []
        for value in sorted(values, key=lambda item: (item.at_ms, item.id)):
            if session and value.at_ms - session[-1].at_ms > GAP_MS:
                topics.extend(_one_session(session, predictions, scope, thread))
                session = []
            session.append(value)
        if session:
            topics.extend(_one_session(session, predictions, scope, thread))
    return tuple(topics)


def _one_session(
    values: list[ExportMessage], predictions: dict[str, Prediction], scope: MemoryScope, thread: str
) -> tuple[Topic, ...]:
    messages = tuple(
        Message(
            item.id, "user", item.text, item.at_ms, scope.owner_id, scope.subject_id, item.revision, thread_id=thread
        )
        for item in values
    )
    return cluster_messages(
        messages,
        {item.id: predictions[item.id] for item in values},
        scope=OrganizeScope(scope.owner_id, scope.subject_id, thread),
    )
