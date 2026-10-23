"""Independent K1/K2, scoped source, sensitive preview and area-grouping expectations."""

from dataclasses import asdict, replace
from datetime import time, timedelta

import pytest
from brief_acceptance_support_mod import BASE, SCOPE, compose, context, item, public_text, source_state

from mingjing_core.application.briefing_v2 import subscription_basis
from mingjing_core.application.followups_contracts import FollowupScope


@pytest.mark.parametrize(("minutes", "expected"), [(-15, "not_due"), (0, "push")])
def test_default_preparation_and_subscribed_seven_oclock_have_distinct_delivery_states(minutes, expected):
    result = compose(context(at=BASE + timedelta(minutes=minutes)))
    assert result.delivery.disposition == expected
    assert result.generated_at == BASE + timedelta(minutes=minutes)
    assert all(value == 0 for value in asdict(result.effects).values())


def test_subscribed_custom_six_oclock_is_not_shifted_to_the_end_of_quiet_hours():
    values = context(at=BASE - timedelta(hours=1))
    subscription = replace(values["subscription"], local_time=time(6))
    result = compose(
        values, subscription=subscription, subscription_state=source_state(subscription_basis(subscription))
    )
    assert result.delivery.allowed and result.delivery.original_due == BASE - timedelta(hours=1)


@pytest.mark.parametrize(
    "guard",
    ["unsubscribed", "global_off", "inactive", "revoked", "incognito", "stale", "missing", "muted", "adaptive_muted"],
)
def test_briefing_quiet_exemption_does_not_bypass_subscription_or_privacy_gates(guard):
    values = context()
    private = item(body="SYNTHETIC_PRIVATE_EVENT")
    values["items"] = (private,)
    if guard == "unsubscribed":
        values["subscription"] = replace(values["subscription"], enabled=False)
        values["subscription_state"] = source_state(subscription_basis(values["subscription"]))
    elif guard == "global_off":
        values["settings"] = replace(values["settings"], proactive_enabled=False)
    elif guard in {"inactive", "revoked", "incognito", "stale"}:
        changes = {
            "inactive": {"active": False},
            "revoked": {"revoked": True},
            "incognito": {"incognito": True},
            "stale": {"revision": 2},
        }[guard]
        values["subscription_state"] = replace(values["subscription_state"], **changes)
    elif guard == "missing":
        values["subscription_state"] = None
    elif guard == "muted":
        values["settings"] = replace(values["settings"], muted_categories=frozenset({"brief"}))
    else:
        values["receptivity"] = replace(values["receptivity"], muted_categories=frozenset({"brief"}))
    result = compose(values)
    assert not result.sections and (result.delivery is None or not result.delivery.allowed)
    assert "SYNTHETIC_PRIVATE_EVENT" not in public_text(result)


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_foreign_subscription_cannot_expose_the_current_owners_content(field):
    values = context()
    foreign = replace(SCOPE, **{field: "other"})
    values["subscription"] = replace(values["subscription"], scope=foreign)
    values["subscription_state"] = source_state(subscription_basis(values["subscription"]))
    with pytest.raises(ValueError) as caught:
        compose(values, items=(item(body="SYNTHETIC_PRIVATE_EVENT"),))
    assert "SYNTHETIC_PRIVATE_EVENT" not in str(caught.value)


@pytest.mark.parametrize(
    "guard",
    [
        "inactive",
        "source_inactive",
        "source_revoked",
        "state_revoked",
        "state_incognito",
        "missing_state",
        "stale_revision",
        "changed_hash",
    ],
)
def test_item_source_guards_prevent_body_from_appearing_in_any_section(guard):
    entry = item(body="SYNTHETIC_REVOKED_BODY")
    candidate = entry.request.candidate
    if guard in {"inactive", "source_inactive", "source_revoked"}:
        changes = {
            "inactive": {"active": False},
            "source_inactive": {"source_active": False},
            "source_revoked": {"source_revoked": True},
        }[guard]
        entry = replace(entry, request=replace(entry.request, candidate=replace(candidate, **changes)))
    elif guard == "missing_state":
        entry = replace(entry, source_states=())
    else:
        changes = {
            "state_revoked": {"revoked": True},
            "state_incognito": {"incognito": True},
            "stale_revision": {"revision": 2},
            "changed_hash": {"value_sha256": "f" * 64},
        }[guard]
        entry = replace(entry, source_states=(replace(entry.source_states[0], **changes),))
    result = compose(context(), items=(entry,))
    assert "SYNTHETIC_REVOKED_BODY" not in public_text(result)
    assert all(ref.source_id != entry.basis[0].source_id for ref in result.basis)


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_foreign_item_or_basis_is_rejected_without_exposing_its_private_text(field):
    entry = item(body="SYNTHETIC_FOREIGN_BODY")
    basis = replace(
        entry.basis[0],
        **{field: "other"},
        document_id="synthetic-private-document",
        path="/private_source/one",
        claim_id="claim-" + "c" * 64,
    )
    foreign = replace(entry, basis=(basis,), source_states=(source_state(basis),))
    forbidden = (entry.request.candidate.text, basis.source_id, basis.document_id, basis.claim_id)
    try:
        result = compose(context(), items=(foreign,))
    except ValueError as error:
        assert all(value not in str(error) for value in forbidden)
        return
    assert all(value not in repr(asdict(result)) for value in forbidden)
    assert not any(ref.source_id == basis.source_id for ref in result.basis)
    assert any(omission.item_id == entry.request.candidate.id for omission in result.omissions)


@pytest.mark.parametrize(
    "change",
    [
        {"source_id": "other"},
        {"scope": FollowupScope("other", SCOPE.subject_id)},
        {"scope": FollowupScope(SCOPE.owner_id, "other")},
        {"value_sha256": "f" * 64},
    ],
)
def test_current_subscription_identity_and_hash_are_required_even_when_enabled(change):
    values = context()
    state = replace(values["subscription_state"], **change)
    result = compose(values, subscription_state=state, items=(item(body="SYNTHETIC_PRIVATE_EVENT"),))
    assert not result.sections and (result.delivery is None or not result.delivery.allowed)
    assert "SYNTHETIC_PRIVATE_EVENT" not in public_text(result)


@pytest.mark.parametrize("change", ["duplicate", "extra", "wrong_state_scope"])
def test_a_current_source_set_cannot_be_ambiguous_or_cross_owner(change):
    entry = item(body="SYNTHETIC_AMBIGUOUS_SOURCE")
    state = entry.source_states[0]
    states = {
        "duplicate": (state, state),
        "extra": (state, replace(state, source_id="another-source")),
        "wrong_state_scope": (replace(state, scope=FollowupScope("other", SCOPE.subject_id)),),
    }[change]
    try:
        result = compose(context(), items=(replace(entry, source_states=states),))
    except ValueError as error:
        assert "SYNTHETIC_AMBIGUOUS_SOURCE" not in str(error)
        return
    assert "SYNTHETIC_AMBIGUOUS_SOURCE" not in public_text(result)
    assert not any(ref.source_id == state.source_id for ref in result.basis)


@pytest.mark.parametrize(("age", "shown"), [(-1, True), (0, True), (3600, True), (3600.000001, False), (3660, False)])
def test_quiet_seven_oclock_reminder_boundaries_are_not_overridden_by_the_brief(age, shown):
    entry = item(due=BASE - timedelta(seconds=age), body="SYNTHETIC_TIMED_REMINDER")
    result = compose(context(), items=(entry,))
    assert ("SYNTHETIC_TIMED_REMINDER" in public_text(result)) == shown


@pytest.mark.parametrize(("age", "shown"), [(43200, True), (43200.000001, False), (46800, False)])
def test_twelve_hour_rule_excludes_old_reminder_from_every_push_section(age, shown):
    at = BASE + timedelta(hours=14)
    entry = item(due=at - timedelta(seconds=age), body="SYNTHETIC_OLD_REMINDER_BODY")
    result = compose(context(at=at), items=(entry,))
    assert ("SYNTHETIC_OLD_REMINDER_BODY" in public_text(result)) == shown
    assert result.effects.notifications == result.effects.scheduler_mutations == 0


@pytest.mark.parametrize(
    ("category", "body"),
    [
        ("health", "SYNTHETIC_HEALTH_DIAGNOSIS"),
        ("finance", "SYNTHETIC_AMOUNT_98765"),
        ("third_party", "SYNTHETIC_OTHER_PERSON"),
    ],
)
def test_sensitive_preview_is_generic_even_when_authorized_content_is_available(category, body):
    result = compose(context(), items=(item(category=category, body=body, sensitive=True),))
    assert body not in result.preview
    assert result.preview and result.effects.notifications == 0


def test_one_local_alias_cannot_refer_to_two_different_current_private_sources():
    first = item(index=1, body="SYNTHETIC_FIRST_PRIVATE_BODY")
    second = item(index=2, body="SYNTHETIC_SECOND_PRIVATE_BODY")
    conflicting = replace(second.basis[0], alias=first.basis[0].alias)
    second = replace(second, basis=(conflicting,))
    with pytest.raises(ValueError) as caught:
        compose(context(), items=(first, second))
    assert first.request.candidate.text not in str(caught.value)
    assert second.request.candidate.text not in str(caught.value)


def test_each_explicit_area_is_distinct_and_unknown_area_is_waiting_for_organization():
    areas = ["daily", "career", "relationships", "family", "wellbeing", "finance", "metaphysics", None]
    entries = tuple(item(index=n, area=area, due=BASE + timedelta(hours=2)) for n, area in enumerate(areas, 1))
    result = compose(context(), items=entries)
    sections = []
    for entry in entries:
        matches = [
            section
            for section in result.sections
            if any(entry.request.candidate.text in line.text for line in section.lines)
        ]
        assert len(matches) == 1
        sections.append(matches[0])
    assert len({section.id for section in sections}) == len(areas)
    assert "待整理" in sections[-1].title
