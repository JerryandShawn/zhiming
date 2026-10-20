"""Evaluation cannot hide abstentions or trust an unrelated owner's context."""

from dataclasses import replace

import pytest

from mingjing_core.organize.contracts import Message
from mingjing_core.organize.v2.contracts import ClassificationContext
from mingjing_core.organize.v2.metrics import classification_metrics
from mingjing_core.organize.v2.scoped import OrganizeScope, ScopedContext, classify_message


def test_selective_denominators_do_not_reward_unknown_gold_assignments():
    metrics = classification_metrics(["career", "finance", None, "career"], ["career", None, "daily", "finance"])
    assert metrics["total"] == 4 and metrics["assigned"] == 3 and metrics["abstentions"] == 1
    assert metrics["assigned_accuracy"] == pytest.approx(1 / 3)
    assert metrics["assigned_accuracy_clear"] == 0.5
    assert metrics["ambiguous_assigned_count"] == 1
    assert metrics["metric_unit"] == "area_assignment"


def test_all_abstentions_are_not_perfect_assigned_accuracy():
    metrics = classification_metrics(["career", "finance"], [None, None])
    assert metrics["assigned_accuracy"] is None and metrics["abstention_rate"] == 1
    assert metrics["ari_assigned"] is None


@pytest.mark.parametrize("gold,predicted", [([], []), (["career"], []), ([True], ["career"])])
def test_bad_evaluation_rows_rejected(gold, predicted):
    with pytest.raises(ValueError):
        classification_metrics(gold, predicted)


def message():
    return Message("m1", "user", "下周参加求职面试", 1, "owner", "self", thread_id="thread1")


def test_scoped_context_foreign_owner_subject_or_thread_never_classified():
    original = message()
    scope = OrganizeScope("owner", "self", "thread1")
    assert classify_message(original, scope=scope).area_id == "career"
    for other in (
        OrganizeScope("other", "self", "thread1"),
        OrganizeScope("owner", "other", "thread1"),
        OrganizeScope("owner", "self", "thread2"),
    ):
        with pytest.raises(ValueError):
            classify_message(original, scope=scope, context=ScopedContext(other, ClassificationContext("finance")))


@pytest.mark.parametrize("change", [{"incognito": True}, {"status": "deleted"}, {"retention_scope": "ephemeral"}])
def test_unavailable_source_cannot_be_routed_into_persistent_organize(change):
    with pytest.raises(ValueError):
        classify_message(replace(message(), **change), scope=OrganizeScope("owner", "self", "thread1"))
