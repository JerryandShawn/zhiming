"""Independent pure-host composition; this is not a PG scheduler or notification integration."""

import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.memory2.archive import plan_archives
from mingjing_core.memory2.contracts import (
    Confirmation,
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.event_time_extended_v2 import absolute_event_candidate_extended
from mingjing_core.memory2.guards import MemoryGuardError, authorize_fact
from mingjing_core.memory2.mutation_contracts import MutationConflict
from mingjing_core.memory2.mutations import apply_plan, plan_write
from mingjing_core.memory2.sensitivity import decide_policy
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest
from mingjing_core.scheduling.delivery_rules import plan_delivery, recheck_delivery
from mingjing_core.timekit.clock import FrozenClock

MATRIX = json.loads((Path(__file__).parent / "fixtures/pipeline_expected_mod.json").read_bytes())
SCOPE = MemoryScope("owner", "self")
NOTICE_SCOPE = FollowupScope("owner", "self")
ZONES = ("Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/Berlin", "Australia/Sydney")
RECEPTIVITY = ReceptivityState("owner", "self")


def source_fact(case, *, recorded_delay=timedelta(minutes=1)):
    source = MemorySource("source", "owner", "self", case["text"], datetime.fromisoformat(case["ref"]))
    anchor = SourceAnchor(source.id, source.revision, 0, len(source.text), source.text)
    fact = MemoryFact(
        "event",
        "owner",
        "self",
        "event",
        source.text,
        (source.id,),
        source.at,
        source.at + recorded_delay,
        anchors=(anchor,),
    )
    return fact, MemorySnapshot(SCOPE, sources=(source,))


def damaged(snapshot, guard):
    source = snapshot.sources[0]
    changes = {
        "inactive": {"active": False},
        "revoked": {"revoked": True},
        "changed_revision": {"revision": 2},
        "wrong_owner": {"owner_id": "other"},
        "wrong_subject": {"subject_id": "other"},
        "incognito": {"incognito": True},
        "assistant": {"role": "assistant", "origin": "system"},
        "import_origin": {"origin": "legacy_import"},
        "optout": {"optout": True},
    }
    sources = () if guard == "missing_source" else (replace(source, **changes[guard]),)
    return replace(snapshot, sources=sources)


def project_and_save(case):
    original, snapshot = source_fact(case)
    candidate = absolute_event_candidate_extended(original, snapshot, tz=case["tz"])
    assert not candidate.needs_clarification and candidate.projected is not None
    projected = candidate.projected
    assert candidate.original == original and candidate.original_source_text == original.anchors[0].quote
    assert candidate.wording.original_text == original.anchors[0].quote
    assert candidate.normalized_source_text == candidate.wording.text
    assert projected.anchors == original.anchors and projected.source_ids == original.source_ids
    clock = FrozenClock(original.recorded_at)
    plan = plan_write(snapshot, projected, scope=SCOPE, operation_id="write", clock=clock)
    assert plan.write_status == "saved" and len(plan.changes) == 1
    outcome = apply_plan(snapshot, plan, clock=clock)
    assert outcome.write_status == "saved"
    replay = apply_plan(outcome.snapshot, plan, clock=clock)
    assert replay.replayed and replay.snapshot == outcome.snapshot
    return candidate, plan, outcome.snapshot


def reminder_request(fact, snapshot):
    # The host must re-read these projections at claim time. A stale prior flag is not authority.
    authorize_fact(fact, snapshot, SCOPE)
    sources = [snapshot.source(identity) for identity in fact.source_ids]
    candidate = FollowupCandidate(
        "reminder",
        fact.owner_id,
        fact.subject_id,
        "reminder",
        fact.event_at,
        category="synthetic_event",
        explicit_requested="请提醒我" in sources[0].text,
        source_active=all(source.active for source in sources),
        source_revoked=any(source.revoked for source in sources),
        text=fact.text,
    )
    return DeliveryRequest("event-occurrence", candidate, fact.event_at)


def delivery(request, now, zone):
    return plan_delivery(
        request, FollowupSettings(timezone=zone), RECEPTIVITY, scope=NOTICE_SCOPE, clock=FrozenClock(now)
    )


def assert_reminder_boundaries(snapshot, zone):
    fact = snapshot.fact("event")
    request = reminder_request(fact, snapshot)
    assert delivery(request, fact.event_at - timedelta(microseconds=1), zone).disposition == "not_due"
    for offset in (timedelta(), timedelta(minutes=60), timedelta(minutes=61), timedelta(hours=12)):
        result = delivery(request, fact.event_at + offset, zone)
        assert result.allowed and result.original_due == fact.event_at
        assert result.late_seconds == offset.total_seconds()
    old = delivery(request, fact.event_at + timedelta(hours=12, microseconds=1), zone)
    assert old.app_inbox_only and not old.allowed and old.original_due == fact.event_at


def archive_and_undo(snapshot):
    fact = snapshot.fact("event")
    before = plan_archives(snapshot, scope=SCOPE, clock=FrozenClock(fact.event_end - timedelta(microseconds=1)))
    assert not before.changes
    clock = FrozenClock(fact.event_end)
    plan = plan_archives(snapshot, scope=SCOPE, clock=clock, operation_id="archive")
    assert len(plan.changes) == 1
    outcome = apply_plan(snapshot, plan, clock=clock)
    archived = outcome.snapshot.fact("event")
    assert archived.status == "archived" and outcome.snapshot.sources == snapshot.sources
    assert archived.anchors == fact.anchors and archived.event_at == fact.event_at
    assert archived.event_end == fact.event_end and archived.text == fact.text
    undone = undo_plan(outcome.snapshot, plan, operation_id="undo-archive")
    assert not undone.conflicts and undone.snapshot.fact("event").status == "active"
    restored, expected = asdict(undone.snapshot.fact("event")), asdict(fact)
    restored.pop("revision"), expected.pop("revision")
    assert restored == expected and undone.snapshot.sources == snapshot.sources
    assert outcome.snapshot.source("source").active and not outcome.snapshot.source("source").revoked


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["category"] == "clear"], ids=lambda row: row["id"]
)
def test_frozen_source_time_to_write_reminder_archive_and_fieldwise_undo_chain(case):
    candidate, _, saved = project_and_save(case)
    expected = datetime.combine(date.fromisoformat(case["date"]), time(case["hour"]), ZoneInfo(case["tz"])).astimezone(
        UTC
    )
    assert candidate.time.start == candidate.time.end == expected
    assert saved.fact("event").event_at == expected and saved.fact("event").event_end == expected
    assert_reminder_boundaries(saved, case["tz"])
    archive_and_undo(saved)


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["category"] == "source_guard"], ids=lambda row: row["id"]
)
def test_original_source_guards_precede_projection_writing_and_new_reminder_authorization(case):
    fact, snapshot = source_fact(case)
    invalid = damaged(snapshot, case["guard"])
    with pytest.raises(MemoryGuardError):
        absolute_event_candidate_extended(fact, invalid, tz=case["tz"])
    with pytest.raises(MemoryGuardError):
        reminder_request(replace(fact, event_at=fact.said_at + timedelta(days=1)), invalid)
    if case["guard"] in {"incognito", "optout"}:
        plan = plan_write(invalid, fact, scope=SCOPE, operation_id="blocked", clock=FrozenClock(fact.recorded_at))
        assert plan.write_status == "stop" and not plan.changes
        assert not apply_plan(invalid, plan).snapshot.facts
    else:
        with pytest.raises(MemoryGuardError):
            plan_write(invalid, fact, scope=SCOPE, operation_id="blocked", clock=FrozenClock(fact.recorded_at))


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["category"] == "clarify"], ids=lambda row: row["id"]
)
def test_non_single_time_or_missing_profile_dependency_ledger_never_becomes_an_event(case):
    fact, snapshot = source_fact(case)
    candidate = absolute_event_candidate_extended(fact, snapshot, tz=case["tz"])
    assert candidate.needs_clarification and candidate.projected is None
    assert candidate.wording.original_text == candidate.wording.text == case["text"]
    assert not snapshot.facts and not snapshot.operations


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["category"] == "policy"], ids=lambda row: row["id"]
)
def test_absolute_dates_do_not_bypass_sensitive_confirmation_or_secret_refusal(case):
    fact, snapshot = source_fact(case)
    candidate = absolute_event_candidate_extended(fact, snapshot, tz=case["tz"])
    assert candidate.projected is not None
    clock = FrozenClock(fact.recorded_at)
    plan = plan_write(snapshot, candidate.projected, scope=SCOPE, operation_id="sensitive", clock=clock)
    assert plan.write_status == case["action"] and not plan.changes
    outcome = apply_plan(snapshot, plan, clock=clock)
    assert not outcome.snapshot.facts
    if case["action"] == "reject":
        return
    repeat = decide_policy(outcome.snapshot, candidate.projected, scope=SCOPE, clock=clock)
    assert not repeat.ask_required and repeat.question_key == plan.question_key
    anchor = fact.anchors[0]
    declined = Confirmation(
        SCOPE,
        anchor.source_id,
        anchor.revision,
        anchor.quote_fingerprint,
        frozenset(case["categories"]),
        "declined",
        clock.now(),
    )
    stopped = plan_write(
        outcome.snapshot, candidate.projected, scope=SCOPE, operation_id="decline", clock=clock, confirmation=declined
    )
    assert stopped.write_status == "stop" and not stopped.changes
    assert not apply_plan(outcome.snapshot, stopped, clock=clock).snapshot.facts


@pytest.mark.parametrize("guard", ["revoked", "changed_revision", "incognito", "wrong_owner", "assistant"])
def test_source_changes_after_write_preparation_block_apply_replay_and_new_reminders(guard):
    case = MATRIX["cases"][0]
    fact, empty = source_fact(case)
    candidate = absolute_event_candidate_extended(fact, empty, tz=case["tz"])
    plan = plan_write(
        empty, candidate.projected, scope=SCOPE, operation_id="write", clock=FrozenClock(fact.recorded_at)
    )
    invalid = damaged(empty, guard)
    with pytest.raises((MemoryGuardError, MutationConflict)):
        apply_plan(invalid, plan, clock=FrozenClock(fact.recorded_at))
    saved = apply_plan(empty, plan, clock=FrozenClock(fact.recorded_at)).snapshot
    withdrawn = damaged(saved, guard)
    replay = apply_plan(withdrawn, plan, clock=FrozenClock(fact.recorded_at))
    assert replay.replayed and replay.write_status == "unavailable"
    with pytest.raises(MemoryGuardError):
        reminder_request(saved.fact("event"), withdrawn)


def test_delayed_extraction_and_a_conflicting_summary_never_move_the_original_source_reference():
    case = MATRIX["cases"][0]
    original, snapshot = source_fact(case, recorded_delay=timedelta(days=40))
    summary = replace(original, text="明年三月开会，这是一个不应决定日期的摘要")
    candidate = absolute_event_candidate_extended(summary, snapshot, tz=case["tz"])
    assert not candidate.needs_clarification
    assert candidate.projected.event_at == datetime(2026, 10, 21, 1, tzinfo=UTC)
    assert candidate.projected.text == summary.text and candidate.original_source_text == original.text


@pytest.mark.parametrize("field", ["event_at", "event_end"])
def test_existing_event_time_conflicts_remain_proposals_instead_of_overwriting_metadata(field):
    fact, snapshot = source_fact(MATRIX["cases"][0])
    already_recorded = replace(fact, **{field: datetime(2026, 10, 21, 1, 1, tzinfo=UTC)})
    candidate = absolute_event_candidate_extended(already_recorded, snapshot)
    assert candidate.needs_clarification and candidate.projected is None
    assert candidate.original == already_recorded


def test_archived_event_undo_cannot_reactivate_a_withdrawn_original_source():
    _, _, saved = project_and_save(MATRIX["cases"][0])
    fact = saved.fact("event")
    clock = FrozenClock(fact.event_end)
    archive = plan_archives(saved, scope=SCOPE, clock=clock, operation_id="archive")
    archived = apply_plan(saved, archive, clock=clock).snapshot
    withdrawn = damaged(archived, "revoked")
    undone = undo_plan(withdrawn, archive, operation_id="undo-withdrawn-archive")
    assert undone.conflicts and undone.snapshot.fact("event").status == "archived"
    assert undone.snapshot.source("source").revoked
    with pytest.raises(MemoryGuardError):
        reminder_request(undone.snapshot.fact("event"), undone.snapshot)


@pytest.mark.parametrize("text", ["明天小王下午三点面试，请提醒我", "明天开会下午三点，请提醒我"])
def test_event_wording_between_date_and_clock_is_not_swallowed_by_a_memory_write_candidate(text):
    case = dict(MATRIX["cases"][0], text=text)
    fact, snapshot = source_fact(case)
    candidate = absolute_event_candidate_extended(fact, snapshot)
    assert candidate.needs_clarification and candidate.projected is None
    assert candidate.wording.original_text == candidate.wording.text == text


@pytest.mark.parametrize(("clock_text", "expected"), [("11:30pm", "push"), ("6pm", "app_inbox")])
def test_quiet_retry_rechecks_original_age_instead_of_rebasing_it_to_eight_am(clock_text, expected):
    case = dict(MATRIX["cases"][0], text=f"tomorrow at {clock_text} 面试，请提醒我")
    _, _, saved = project_and_save(case)
    fact = saved.fact("event")
    request = reminder_request(fact, saved)
    night = datetime(2026, 10, 18, 16, 31, tzinfo=UTC)
    deferred = delivery(request, night, "Asia/Shanghai")
    assert deferred.disposition == "deferred" and deferred.next_due == datetime(2026, 10, 19, tzinfo=UTC)
    retry = replace(request, not_before=deferred.next_due)
    result = recheck_delivery(
        deferred, retry, FollowupSettings(), RECEPTIVITY, scope=NOTICE_SCOPE, clock=FrozenClock(deferred.next_due)
    )
    assert result.disposition == expected and result.original_due == fact.event_at
    assert result.late_seconds == (deferred.next_due - fact.event_at).total_seconds()
    shifted = replace(
        request, candidate=replace(request.candidate, due_at=deferred.next_due), original_due=deferred.next_due
    )
    with pytest.raises(ValueError):
        recheck_delivery(
            deferred, shifted, FollowupSettings(), RECEPTIVITY, scope=NOTICE_SCOPE, clock=FrozenClock(deferred.next_due)
        )


def test_sensitive_consent_must_bind_original_quote_not_the_absolutized_rewrite():
    case = next(row for row in MATRIX["cases"] if row["category"] == "policy" and row["categories"] == ["health"])
    fact, empty = source_fact(case)
    candidate = absolute_event_candidate_extended(fact, empty)
    clock = FrozenClock(fact.recorded_at)
    first = plan_write(empty, candidate.projected, scope=SCOPE, operation_id="ask", clock=clock)
    asked = apply_plan(empty, first, clock=clock).snapshot
    anchor = fact.anchors[0]
    grant = Confirmation(
        SCOPE,
        anchor.source_id,
        anchor.revision,
        anchor.quote_fingerprint,
        frozenset({"health"}),
        "granted",
        clock.now(),
    )
    rewritten = replace(grant, quote_fingerprint=sha256(candidate.normalized_source_text.encode("utf-8")).hexdigest())
    wrong = plan_write(
        asked, candidate.projected, scope=SCOPE, operation_id="wrong-grant", clock=clock, confirmation=rewritten
    )
    assert wrong.write_status == "proposal" and not wrong.changes
    authorized = plan_write(
        asked, candidate.projected, scope=SCOPE, operation_id="confirmed", clock=clock, confirmation=grant
    )
    assert authorized.write_status == "saved" and len(authorized.changes) == 1
    saved = apply_plan(asked, authorized, clock=clock).snapshot
    assert_reminder_boundaries(saved, "Asia/Shanghai")
    archive_and_undo(saved)


@pytest.mark.parametrize("seed", range(40))
def test_1000_random_reference_dates_zones_and_midnight_boundaries_complete_the_full_pure_chain(seed):
    rng = Random(782613 + seed)
    for _ in range(25):
        zone = ZoneInfo(rng.choice(ZONES))
        local = date(2024, 1, 1) + timedelta(days=rng.randrange(365 * 5))
        ref = datetime.combine(local, time(rng.choice([0, 12, 23]), rng.choice([0, 1, 59])), zone)
        case = {"text": "tomorrow at 9am 面试，请提醒我", "ref": ref.isoformat(), "tz": zone.key}
        candidate, _, saved = project_and_save(case)
        expected = datetime.combine(local + timedelta(days=1), time(9), zone).astimezone(UTC)
        assert candidate.projected.event_at == candidate.projected.event_end == expected
        assert_reminder_boundaries(saved, zone.key)
        archive_and_undo(saved)
