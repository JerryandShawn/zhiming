from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta

import pytest

from mingjing_core.organize.changes import MemoryChangeStore
from mingjing_core.organize.contracts import Message
from mingjing_core.organize.engine import OrganizeEngine
from mingjing_core.organize.review_gate import (
    ReviewApproval,
    approved_changeset,
    preview_organization,
)
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime.fromisoformat("2026-10-27T10:00:00+08:00")
CLOCK = FrozenClock(NOW)


def setup():
    message = Message(
        "synthetic-m1", "user", "合成求职面试准备", 1, "synthetic-owner", "self"
    )
    document = {
        "owner_id": message.owner_id,
        "subject_id": message.subject_id,
        "messages": {message.id: asdict(message)},
        "topics": {},
    }
    proposal = OrganizeEngine().organize([message])
    preview = preview_organization(proposal, document, batch_id="synthetic-batch")
    approval = ReviewApproval(
        "synthetic-user-approval",
        preview.batch_id,
        preview.owner_id,
        preview.subject_id,
        preview.fingerprint,
        NOW,
        True,
    )
    return document, proposal, preview, approval


def test_review_first_adds_only_labels_and_field_exact_revert():
    original, proposal, preview, approval = setup()
    before = deepcopy(original)
    assert preview.summary["spaces"] and original == before
    store = MemoryChangeStore(original)
    plan = approved_changeset(proposal, original, approval, clock=CLOCK)
    actual = store.apply(plan)
    assert actual != original
    assert (
        actual["messages"]["synthetic-m1"]["content"]
        == original["messages"]["synthetic-m1"]["content"]
    )
    assert store.revert(plan.batch_id) == original == before
    assert "合成求职" not in repr(preview)


@pytest.mark.parametrize(
    "change",
    [
        {"accepted": False},
        {"owner_id": "foreign"},
        {"subject_id": "foreign"},
        {"batch_id": "other"},
        {"fingerprint": "changed"},
        {"reviewed_at": NOW + timedelta(seconds=1)},
        {"reviewed_at": NOW - timedelta(hours=24, seconds=1)},
    ],
)
def test_approval_is_bound_to_exact_user_scope_batch_plan_and_time(change):
    document, proposal, _, approval = setup()
    with pytest.raises(ValueError):
        approved_changeset(proposal, document, replace(approval, **change), clock=CLOCK)


def test_edit_after_review_requires_review_again():
    document, proposal, _, approval = setup()
    changed = proposal.rename(proposal.topics[0].id, "合成改名")
    with pytest.raises(ValueError, match="reviewed plan changed"):
        approved_changeset(changed, document, approval, clock=CLOCK)


def test_changed_or_revoked_source_never_reaches_application():
    for change in ({"content": "changed"}, {"revision": 2}, {"status": "revoked"}):
        document, proposal, _, approval = setup()
        document["messages"]["synthetic-m1"].update(change)
        with pytest.raises(ValueError):
            approved_changeset(proposal, document, approval, clock=CLOCK)


def test_existing_label_is_preserved_and_null_is_reversible():
    document, proposal, _, approval = setup()
    document["messages"]["synthetic-m1"]["route_source"] = "user"
    with pytest.raises(ValueError, match="overwrite"):
        preview_organization(proposal, document, batch_id=approval.batch_id)
    document["messages"]["synthetic-m1"]["route_source"] = None
    preview = preview_organization(proposal, document, batch_id=approval.batch_id)
    plan = approved_changeset(
        proposal,
        document,
        replace(approval, fingerprint=preview.fingerprint),
        clock=CLOCK,
    )
    store = MemoryChangeStore(document)
    store.apply(plan)
    assert store.revert(plan.batch_id) == document


def test_forged_boolean_is_rejected_and_no_approval_is_inferred():
    document, proposal, _, approval = setup()
    with pytest.raises(ValueError):
        replace(approval, accepted=1)
    with pytest.raises(ValueError):
        approved_changeset(proposal, document, None, clock=CLOCK)
