"""One-day P8 evidence remains one day; synthetic examples cannot impersonate chart claims."""

from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from mingjing_core.application.briefing_v2.contracts import BriefingError
from mingjing_core.application.reports_v2 import DailyTransitInput, ReportError

from .calendar_acceptance_support_mod import (
    DAY,
    p8_payload,
    p8_report,
    p8_scope,
    p8_state,
    rendered,
    report,
    symbolic,
)


@pytest.mark.parametrize("kind,days", (("weekly", 7), ("monthly", 31), ("quarterly", 92)))
def test_single_p8_noon_snapshot_cannot_become_whole_period_evidence(kind: str, days: int) -> None:
    payload = p8_payload()
    result = p8_report(payload, kind=kind)
    assert result.coverage.period_days == days
    assert result.coverage.rendered_snapshot_days == (DAY,)
    assert result.coverage.synthetic_days == ()
    assert result.used_claim_ids
    displayed = {
        citation.basis.claim_id
        for section in result.sections
        for line in section.lines
        for citation in line.citations
        if citation.basis.claim_id is not None
    }
    assert set(result.used_claim_ids) == displayed
    assert len(result.coverage.rendered_snapshot_days) < result.coverage.period_days
    assert not result.effects.model_calls and not result.effects.notifications


def test_p8_aliases_retain_original_document_pointer_hash_and_claim() -> None:
    payload = p8_payload()
    result = p8_report(payload)
    originals = {row["claim_id"]: row for rows in payload["aliases"].values() for row in rows}
    for citation in result.citations:
        ref = citation.basis
        if ref.claim_id is None:
            continue
        origin = originals[ref.claim_id]
        assert citation.source_alias == origin["alias"]
        assert ref.document_id == payload["document_id"]
        assert ref.path == origin["path"] and ref.value_sha256 == origin["value_sha256"]
        assert (ref.owner_id, ref.subject_id, ref.revision) == (
            result.scope.owner_id,
            result.scope.subject_id,
            payload["scope"]["revision"],
        )
    assert set(result.used_claim_ids) <= set(originals)


@pytest.mark.parametrize(
    "change",
    (
        "current_missing",
        "current_revoked",
        "current_inactive",
        "current_incognito",
        "current_revision",
        "current_hash",
        "current_source",
        "current_owner",
        "profile_revision",
        "input_day",
        "declared_date",
        "noon",
        "document",
        "owner",
        "subject",
        "effect_bool",
        "unknown_root",
    ),
)
def test_p8_scope_current_date_noon_and_document_mismatch_never_render(change: str) -> None:
    payload = p8_payload()
    scope, current, revision, input_day = p8_scope(payload), p8_state(payload), 1, DAY
    if change.startswith("current_"):
        modifications = {
            "current_revoked": {"revoked": True},
            "current_inactive": {"active": False},
            "current_incognito": {"incognito": True},
            "current_revision": {"revision": 2},
            "current_hash": {"value_sha256": "0" * 64},
            "current_source": {"source_id": "synthetic-other-document"},
            "current_owner": {"scope": replace(scope, owner_id="synthetic-other-owner")},
        }
        current = None if change == "current_missing" else replace(current, **modifications[change])
    elif change == "profile_revision":
        revision = 2
    elif change == "input_day":
        input_day = date(2026, 10, 22)
    else:
        mutate_p8_payload(payload, change)
    try:
        result = report(
            scope=scope,
            transits=(DailyTransitInput(input_day, payload, current),),
            profile_revision=revision,
        )
    except (ReportError, BriefingError):
        return
    assert result.coverage.rendered_snapshot_days == ()
    assert result.used_claim_ids == ()
    assert not any(citation.basis.document_id == payload["document_id"] for citation in result.citations)


def mutate_p8_payload(payload: dict[str, Any], change: str) -> None:
    if change == "declared_date":
        payload["data"]["date"] = "2026-10-22"
    elif change == "noon":
        payload["data"]["snapshot_at"] = "2026-10-21T11:00:00+08:00"
    elif change == "document":
        payload["document_id"] = "tool-" + "f" * 64
    elif change in {"owner", "subject"}:
        key = "owner_user_id" if change == "owner" else "subject_id"
        payload["scope"][key] = f"synthetic-other-{change}"
    elif change == "effect_bool":
        payload["effects"]["model_calls"] = False
    elif change == "unknown_root":
        payload["unknown"] = True
    else:
        raise AssertionError("unknown independent mutation")


def test_missing_profile_revision_cannot_accept_otherwise_valid_p8() -> None:
    result = p8_report(p8_payload(), profile_revision=None)
    assert result.coverage.rendered_snapshot_days == () and not result.used_claim_ids


def test_snapshot_outside_current_period_is_not_counted_or_extrapolated() -> None:
    result = p8_report(p8_payload(), kind="monthly", day=date(2026, 11, 1))
    assert result.coverage.rendered_snapshot_days == () and not result.used_claim_ids


def test_valid_synthetic_symbolic_is_explicit_separate_from_p8_and_has_no_chart_claim() -> None:
    row = symbolic()
    result = report(synthetic_symbolic=(row,))
    assert row.text in rendered(result)
    assert result.coverage.synthetic_days == (DAY,) and result.coverage.rendered_snapshot_days == ()
    assert not result.used_claim_ids
    matches = [section for section in result.sections if any(row.text in line.text for line in section.lines)]
    assert len(matches) == 1 and matches[0].category == "synthetic_symbolic"


@pytest.mark.parametrize("flag", (False, 0, 1, None, "true"))
def test_synthetic_flag_must_be_explicit_true_boolean(flag: object) -> None:
    with pytest.raises((ReportError, BriefingError)):
        symbolic(synthetic=flag)


@pytest.mark.parametrize("change", ("source_prefix", "chart_claim"))
def test_synthetic_example_cannot_borrow_real_chart_source_or_claim(change: str) -> None:
    row = symbolic()
    ref = replace(
        row.basis[0],
        **({"source_id": "real-looking-source"} if change == "source_prefix" else {"claim_id": "claim-" + "a" * 64}),
    )
    with pytest.raises((ReportError, BriefingError)):
        replace(row, basis=(ref,))


@pytest.mark.parametrize("changes", ({"active": False}, {"revoked": True}, {"incognito": True}, {"revision": 2}))
def test_synthetic_current_source_guard_still_applies(changes: dict[str, Any]) -> None:
    row = symbolic()
    row = replace(row, source_states=(replace(row.source_states[0], **changes),))
    result = report(synthetic_symbolic=(row,))
    assert row.text not in rendered(result) and not result.coverage.synthetic_days
