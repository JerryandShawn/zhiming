"""Independent intent oracle: fixture predates memory2 policy implementation."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mingjing_core.memory2.contracts import (
    Confirmation,
    MemoryFact,
    MemoryScope,
    MemorySettings,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.sensitivity import decide_policy
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, 0, tzinfo=UTC)
SCOPE = MemoryScope("owner", "self")
TRUTH = json.loads((Path(__file__).parent / "fixtures/acceptance_policy_expected_mod.json").read_text("utf-8"))


def case(text, *, kind="background", source_id="source", fact_id="fact"):
    source = MemorySource(source_id, "owner", "self", text, AT)
    anchor = SourceAnchor(source_id, 1, 0, len(text), text)
    fact = MemoryFact(fact_id, "owner", "self", kind, text, (source_id,), AT, AT, anchors=(anchor,))
    return fact, MemorySnapshot(SCOPE, sources=(source,))


def decision(fact, snapshot, **kwargs):
    return decide_policy(snapshot, fact, scope=SCOPE, clock=FrozenClock(AT), **kwargs)


def grant(fact, categories):
    anchor = fact.anchors[0]
    return Confirmation(
        SCOPE,
        anchor.source_id,
        anchor.revision,
        anchor.quote_fingerprint,
        frozenset(categories),
        "granted",
        AT,
    )


@pytest.mark.parametrize("text", TRUTH["optout"])
def test_explicit_user_optout_always_stops(text):
    fact, snapshot = case(text)
    result = decision(fact, snapshot, settings=MemorySettings({"health", "finance", "third_party"}))
    assert result.action == "stop"
    assert not result.ask_required


@pytest.mark.parametrize("text", TRUTH["non_optout"])
def test_negation_and_quoted_text_do_not_invent_optout(text):
    fact, snapshot = case(text)
    assert decision(fact, snapshot).action == "save"


@pytest.mark.parametrize(
    "category,text",
    [(k, text) for k, values in TRUTH["sensitive"].items() for text in values],
)
def test_sensitive_intent_is_a_proposal_and_asks_only_once(category, text):
    fact, snapshot = case(text)
    first = decision(fact, snapshot)
    assert first.action == "proposal", category
    assert first.categories and first.ask_required and first.question_key
    later = replace(snapshot, asked_keys=(first.question_key,))
    second = decision(fact, later)
    assert second.action == "proposal" and not second.ask_required
    assert second.question_key == first.question_key
    assert not snapshot.facts and not later.facts


@pytest.mark.parametrize("text", TRUTH["profile_confirmation"])
def test_own_birth_data_uses_explicit_profile_confirmation(text):
    fact, snapshot = case(text)
    assert decision(fact, snapshot).action == "profile_confirm"


@pytest.mark.parametrize("text", ["我确诊了哮喘。", "我现在欠款八万元。", "我同事小张正在离婚。"])
def test_sensitive_confirmation_is_bound_to_exact_source_scope_and_content(text):
    fact, snapshot = case(text)
    categories = decision(fact, snapshot).categories
    consent = grant(fact, categories)
    assert decision(fact, snapshot, confirmation=consent).action == "save"
    invalid = (
        replace(consent, scope=MemoryScope("another", "self")),
        replace(consent, source_id="different"),
        replace(consent, source_revision=2),
        replace(consent, quote_fingerprint="0" * 64),
        replace(consent, categories=frozenset()),
        replace(consent, at=AT + timedelta(seconds=1)),
        replace(consent, at=AT - timedelta(seconds=1)),
    )
    assert all(decision(fact, snapshot, confirmation=item).action == "proposal" for item in invalid)
    assert decision(fact, snapshot, confirmation=replace(consent, decision="declined")).action == "stop"


def test_consent_does_not_authorize_another_message_or_multi_source_fact():
    first, original = case("我确诊了哮喘。")
    consent = grant(first, decision(first, original).categories)
    second, later = case("我确诊了哮喘。", source_id="different", fact_id="new")
    assert decision(second, later, confirmation=consent).action == "proposal"
    multi = replace(
        first,
        source_ids=("source", "different"),
        anchors=first.anchors + second.anchors,
    )
    combined = replace(original, sources=original.sources + later.sources)
    assert decision(multi, combined, confirmation=consent).action == "proposal"


def test_preapproved_category_does_not_authorize_other_category_or_model_hint():
    health, health_state = case("我确诊了哮喘。")
    permitted = MemorySettings(decision(health, health_state).categories)
    assert decision(health, health_state, settings=permitted).action == "save"
    debt, debt_state = case("我欠银行二十万元。")
    assert decision(debt, debt_state, settings=permitted).action == "proposal"
    combined, mixed_state = case("我确诊了哮喘，而且欠银行二十万元。")
    assert decision(combined, mixed_state, settings=permitted).action == "proposal"
    assert decision(health, health_state, settings=permitted, model_hint=("sensitive",)).action == "proposal"


@pytest.mark.parametrize("text", ["我的密码是合成例子X9。", "我的身份证号码是110101199001010011。"])
def test_secret_is_never_saved_even_with_category_consent(text):
    fact, snapshot = case(text)
    assert decision(fact, snapshot).action == "reject"
    consent = grant(fact, ())
    assert decision(fact, snapshot, confirmation=consent).action == "reject"


@pytest.mark.parametrize(
    "flag,value",
    [
        ("revoked", True),
        ("active", False),
        ("role", "assistant"),
        ("owner_id", "other"),
        ("subject_id", "other"),
        ("revision", 2),
    ],
)
def test_source_revalidation_precedes_prior_authorization(flag, value):
    fact, snapshot = case("我确诊了哮喘。")
    consent = grant(fact, decision(fact, snapshot).categories)
    stale = replace(
        snapshot,
        sources=(replace(snapshot.sources[0], **{flag: value}),),
        source_epoch=1,
    )
    with pytest.raises(MemoryGuardError):
        decision(fact, stale, confirmation=consent)


@pytest.mark.parametrize("flag", ["incognito", "optout"])
def test_explicit_source_privacy_wins_over_preauthorization(flag):
    fact, snapshot = case("我确诊了哮喘。")
    consent = grant(fact, decision(fact, snapshot).categories)
    private = replace(snapshot, sources=(replace(snapshot.sources[0], **{flag: True}),))
    assert decision(fact, private, confirmation=consent).action == "stop"


def test_continuous_literal_source_anchor_is_required():
    fact, snapshot = case("我希望住得离学校近一点。")
    forged = replace(fact, anchors=(replace(fact.anchors[0], quote="我已经住在学校旁边。"),))
    with pytest.raises(MemoryGuardError):
        decision(forged, snapshot)


def test_assistant_claim_cannot_be_promoted_to_user_fact():
    fact, snapshot = case("建议你先做一页作品集。")
    claim = replace(fact, origin="assistant_claim")
    with pytest.raises(MemoryGuardError):
        decision(claim, snapshot)
