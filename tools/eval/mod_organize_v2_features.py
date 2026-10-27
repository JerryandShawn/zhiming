"""Scoped feature projection for final evaluation; no gold label enters the classifier."""

from mingjing_core.organize.v2.contracts import ClassificationContext
from mingjing_core.organize.v2.metrics import classification_metrics
from mingjing_core.organize.v2.scoped import ScopedContext, classify_message

from .mod_organize_v2_topics import message_from_record, scope_for, topic_metrics


def predict_record(record, classifier, contexts):
    message = message_from_record(record)
    scope = scope_for(message)
    group = record.get("context_group")
    key = (scope, group) if isinstance(group, str) and group else None
    context = contexts.get(key) if key is not None else None
    scoped = ScopedContext(scope, context) if context else None
    prediction = classify_message(message, scope=scope, context=scoped, classifier=classifier)
    if key is not None:
        recent = (*context.recent_texts, message.content)[-3:] if context else (message.content,)
        contexts[key] = ClassificationContext(
            previous_area_id=prediction.area_id,
            previous_confidence=prediction.confidence,
            recent_texts=recent,
            previous_text=message.content,
        )
    return (scope, message.id), prediction


def evaluate_records(
    records,
    classifier,
    normalization,
    *,
    similarity_threshold=0.4,
    unknown_gold="__unorganized__",
    error_type=ValueError,
):
    contexts, gold, predicted, predictions = {}, [], [], {}
    for record in records:
        if (
            not isinstance(record.get("content"), str)
            or not isinstance(record.get("owner_id"), str)
            or not isinstance(record.get("subject_id"), str)
        ):
            raise error_type("blind_message_shape_invalid")
        identity, prediction = predict_record(record, classifier, contexts)
        if prediction.area_id is not None and prediction.area_id not in set(normalization.values()):
            raise error_type("blind_prediction_namespace_invalid")
        if identity in predictions:
            raise error_type("blind_duplicate_scoped_message")
        predictions[identity] = prediction
        predicted.append(prediction.area_id)
        # The expected label is deliberately unavailable until after this prediction.
        expected = record.get("expected_space")
        if expected is not None and expected not in normalization:
            raise error_type("blind_gold_namespace_invalid")
        gold.append(unknown_gold if expected is None else normalization[expected])
    return {
        "area_assignment": classification_metrics(gold, predicted),
        **topic_metrics(records, predictions, similarity_threshold=similarity_threshold),
        "gold_unknown_policy": "fixed_unorganized_label_no_records_dropped",
        "context_policy": "input_order_within_explicit_owner_subject_thread_context_group_using_prior_predictions_only",
    }
