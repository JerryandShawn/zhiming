"""Independent source/owner/revocation and full-origin citation invariants."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.application.reports_v2 import ReportError, ReportRecord

from .calendar_acceptance_support_mod import (
    NOW,
    SCOPE,
    p8_payload,
    p8_scope,
    p8_state,
    record,
    record_citations,
    rendered,
    report,
    symbolic,
    wording,
)


def assert_omitted(row: ReportRecord) -> None:
    try:
        result = report(records=(row,))
    except ReportError as error:
        assert row.text not in str(error)
        return
    assert row.id not in result.used_record_ids
    assert row.text not in rendered(result)
    assert not record_citations(result, row.basis[0].source_id)


@pytest.mark.parametrize("field", ("owner_id", "subject_id"))
def test_foreign_record_scope_error_never_returns_private_ids_or_body(field: str) -> None:
    scope = replace(SCOPE, **{field: f"synthetic-foreign-{field}"})
    row = record(scope=scope, id="synthetic-foreign-record", text=wording("foreign"))
    with pytest.raises(ReportError) as caught:
        report(records=(row,))
    assert row.text not in str(caught.value)
    assert row.id not in str(caught.value)
    assert getattr(scope, field) not in str(caught.value)


@pytest.mark.parametrize(
    "changes",
    (
        {"active": False},
        {"revoked": True},
        {"incognito": True},
        {"revision": 2},
        {"value_sha256": "f" * 64},
        {"source_id": "synthetic-other-source"},
        {"scope": FollowupScope("synthetic-other-owner", SCOPE.subject_id)},
        {"scope": FollowupScope(SCOPE.owner_id, "synthetic-other-subject")},
    ),
)
def test_invalid_current_source_is_not_rendered(changes: dict[str, Any]) -> None:
    row = record()
    assert_omitted(replace(row, source_states=(replace(row.source_states[0], **changes),)))


def test_missing_current_source_is_not_rendered() -> None:
    assert_omitted(record(source_states=()))


@pytest.mark.parametrize("changes", ({"status": "retired"}, {"status": "deleted"}, {"status": "archived"}))
def test_retired_deleted_archived_user_facts_are_not_promoted(changes: dict[str, str]) -> None:
    assert_omitted(record(**changes))


@pytest.mark.parametrize(
    "changes",
    (
        {"origin": "assistant_claim"},
        {"valid_to": NOW},
        {"valid_to": NOW - timedelta(microseconds=1)},
        {"valid_from": NOW + timedelta(microseconds=1)},
        {"said_at": NOW + timedelta(microseconds=1)},
    ),
)
def test_nonassertion_or_invalid_current_time_record_is_not_promoted(changes: dict[str, Any]) -> None:
    assert_omitted(record(**changes))


def test_validity_start_is_inclusive_and_future_end_remains_active() -> None:
    row = record(valid_from=NOW, valid_to=NOW + timedelta(seconds=1))
    result = report(records=(row,))
    assert row.id in result.used_record_ids and row.text in rendered(result)


@pytest.mark.parametrize(
    "changes",
    (
        {"active": False},
        {"revoked": True},
        {"incognito": True},
        {"revision": 2},
        {"value_sha256": "e" * 64},
        {"scope": FollowupScope("synthetic-other-owner", SCOPE.subject_id)},
    ),
)
@pytest.mark.parametrize("reverse", (False, True))
def test_same_source_conflicting_current_manifest_fails_closed(changes: dict[str, Any], reverse: bool) -> None:
    one = record()
    two = record(2, source_states=(replace(one.source_states[0], **changes),))
    rows = (two, one) if reverse else (one, two)
    try:
        result = report(records=rows)
    except ReportError as error:
        assert one.text not in str(error) and two.text not in str(error)
        return
    assert one.id not in result.used_record_ids
    assert one.text not in rendered(result)


def test_source_manifest_consistency_crosses_record_and_synthetic_categories() -> None:
    sym = symbolic()
    one = record(basis=sym.basis, source_states=sym.source_states)
    changed = replace(sym, source_states=(replace(sym.source_states[0], revoked=True),))
    with pytest.raises(ReportError):
        report(records=(one,), synthetic_symbolic=(changed,))


def test_source_manifest_consistency_crosses_record_and_transit_categories() -> None:
    from mingjing_core.application.reports_v2 import DailyTransitInput

    payload = p8_payload()
    scope, current = p8_scope(payload), p8_state(payload)
    ref = replace(record().basis[0], source_id=current.source_id, owner_id=scope.owner_id, subject_id=scope.subject_id)
    one = record(scope=scope, basis=(ref,), source_states=(replace(current, revoked=True),))
    with pytest.raises(ReportError):
        report(
            scope=scope,
            records=(one,),
            transits=(DailyTransitInput(datetime(2026, 10, 21).date(), payload, current),),
            profile_revision=1,
        )


def test_same_original_alias_gets_distinct_local_alias_and_keeps_full_origin() -> None:
    one, two = record(), record(2)
    result = report(records=(one, two))
    citations = tuple(record_citations(result, row.basis[0].source_id)[0] for row in (one, two))
    assert len({citation.local_alias for citation in citations}) == 2
    assert tuple(citation.source_alias for citation in citations) == ("f1", "f1")
    assert tuple(citation.basis for citation in citations) == (one.basis[0], two.basis[0])
    structured = {
        citation.local_alias for section in result.sections for line in section.lines for citation in line.citations
    }
    assert {citation.local_alias for citation in citations} <= structured


def test_omitted_sources_do_not_enter_used_claims_or_citations() -> None:
    one, two = record(), record(2)
    ref = replace(two.basis[0], claim_id="claim-" + "a" * 64)
    two = replace(two, basis=(ref,), source_states=(replace(two.source_states[0], revoked=True),))
    result = report(records=(one, two))
    assert one.id in result.used_record_ids and two.id not in result.used_record_ids
    assert ref.claim_id not in result.used_claim_ids
    assert not record_citations(result, ref.source_id)
    assert two.text not in rendered(result)


def test_duplicate_identical_source_manifest_is_consistent_not_conflicting() -> None:
    one, two = record(), record(2)
    two = replace(two, basis=one.basis, source_states=one.source_states)
    result = report(records=(one, two))
    assert set(result.used_record_ids) == {one.id, two.id}
