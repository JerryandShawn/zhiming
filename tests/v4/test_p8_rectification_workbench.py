"""Frozen evidence and cache contracts reject mutation and scope leakage."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.adapters.charts.rectification_workbench.contracts import (
    AnnualSignalCache,
    canonical,
    digest,
    rules,
)
from mingjing_core.adapters.charts.rectification_workbench.evaluation import (
    generated_events,
    session,
    synthetic_cache,
)
from mingjing_core.adapters.charts.rectification_workbench.sessions import (
    FrozenSession,
    events_digest,
    freeze_round1,
    freeze_round2,
    revoke_event,
    split_events,
)
from mingjing_core.adapters.charts.rectification_workbench.statistics import (
    assess_statistics,
)

Fixture = tuple[AnnualSignalCache, list[dict[str, Any]], FrozenSession]


@pytest.fixture
def fixture() -> Fixture:
    cache = synthetic_cache(0, "contract-tests")
    rows = generated_events(cache, known=None, seed_value=42)
    return cache, rows, session(cache, rows, "frozen-session")


def addition(**updates: Any) -> dict[str, Any]:
    return {
        "id": "new-second-round",
        "source_fact_id": "new-source",
        "type": "career",
        "year": 2000,
        "added_in_round": 2,
        **updates,
    }


def test_hash_is_canonical_normalized_event_json_not_string_list(
    fixture: Fixture,
) -> None:
    cache, rows, frozen = fixture
    backwards = [dict(reversed(list(row.items()))) for row in reversed(rows)]
    reordered = session(cache, backwards, frozen.session_id)
    assert frozen == reordered
    assert frozen.events_hash == digest([json.loads(row) for row in frozen.first])
    assert frozen.events_hash != digest(list(frozen.first))
    with pytest.raises(ValueError):
        canonical({"unserializable_number": float("nan")})


def test_old_event_year_mutation_is_detected_even_in_valid_range(
    fixture: Fixture,
) -> None:
    _, _, frozen = fixture
    changed = json.loads(frozen.first[0])
    changed["year"] += 1
    tampered = replace(frozen, first=(canonical(changed), *frozen.first[1:]))
    with pytest.raises(ValueError, match="frozen_events_changed"):
        tampered.verify()


def test_rule_hash_drift_invalidates_frozen_session(fixture: Fixture) -> None:
    _, _, frozen = fixture
    with pytest.raises(ValueError, match="frozen_rules_changed"):
        replace(frozen, rules_hash="another-version").verify()


def test_second_round_preserves_round_one_and_replay_is_idempotent(
    fixture: Fixture,
) -> None:
    cache, _, frozen = fixture
    original = assess_statistics(frozen, cache)
    second = freeze_round2(frozen, [addition()], user_confirmed=True)
    assert second.first == frozen.first
    assert second.events_hash == frozen.events_hash
    assert second.round2_hash == events_digest(second.second)
    assert freeze_round2(second, [addition()], user_confirmed=True) is second
    rerun = assess_statistics(second, cache)
    assert {k: v for k, v in original.items() if k != "null_seconds"} == {
        k: v for k, v in rerun.items() if k != "null_seconds"
    }
    assert assess_statistics(second, cache, 2)["alpha"] == 0.025


def test_third_round_and_editing_second_round_year_are_rejected(
    fixture: Fixture,
) -> None:
    _, _, frozen = fixture
    second = freeze_round2(frozen, [addition()], user_confirmed=True)
    with pytest.raises(ValueError, match="maximum_two_rounds"):
        freeze_round2(second, [addition(year=2001)], user_confirmed=True)
    with pytest.raises(ValueError, match="maximum_two_rounds"):
        second.event_rows(3)


@pytest.mark.parametrize("field", ["id", "source_fact_id"])
def test_repeated_event_or_source_cannot_enter_round_two(
    fixture: Fixture,
    field: str,
) -> None:
    _, rows, frozen = fixture
    with pytest.raises(ValueError, match="replaced_or_repeated"):
        freeze_round2(
            frozen, [addition(**{field: rows[0][field]})], user_confirmed=True
        )


def test_duplicate_source_in_first_round_is_rejected(fixture: Fixture) -> None:
    cache, rows, _ = fixture
    rows[1]["source_fact_id"] = rows[0]["source_fact_id"]
    with pytest.raises(ValueError, match="duplicate_or_invalid_event_source"):
        session(cache, rows, "duplicate-first")


@pytest.mark.parametrize("confirmation", [False, None, 1, "yes"])
def test_only_explicit_boolean_confirmation_freezes(
    fixture: Fixture,
    confirmation: object,
) -> None:
    cache, rows, _ = fixture
    with pytest.raises(ValueError, match="explicit_user_confirmation"):
        freeze_round1(
            "unconfirmed",
            rows,
            owner_user_id=cache.scope[0],
            subject_id=cache.scope[1],
            revision=cache.scope[2],
            birth_year=cache.birth_year,
            as_of_year=cache.as_of_year,
            user_confirmed=confirmation,
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"year": 1985},
        {"year": 2027},
        {"year": True},
        {"type": "education", "year": 2020},
        {"month": 0},
        {"month": 13},
        {"month": True},
        {"certainty": "certain"},
        {"added_in_round": 2},
    ],
)
def test_invalid_event_metadata_never_freezes(
    fixture: Fixture,
    updates: dict[str, Any],
) -> None:
    cache, rows, _ = fixture
    with pytest.raises(ValueError):
        session(cache, [dict(rows[0], **updates)], "invalid-metadata")


def test_missing_month_and_certainty_are_preserved_as_unknown(fixture: Fixture) -> None:
    cache, rows, _ = fixture
    row = dict(rows[0])
    row.pop("certainty")
    normalized = session(cache, [row], "unknown-month").event_rows(1)[0]
    assert normalized["month"] is None
    assert normalized["certainty"] == "unsure"


def test_revocation_keeps_audit_but_invalidates_results(fixture: Fixture) -> None:
    cache, rows, frozen = fixture
    with pytest.raises(ValueError, match="revocation_reason"):
        revoke_event(frozen, rows[0]["id"], " ")
    revoked = revoke_event(frozen, rows[0]["id"], "source corrected")
    assert frozen.revocations == ()
    assert json.loads(revoked.revocations[0])["reason"] == "source corrected"
    with pytest.raises(ValueError, match="basis_revoked"):
        assess_statistics(revoked, cache)


def test_holdout_is_session_seeded_one_third_without_overlap(fixture: Fixture) -> None:
    _, _, frozen = fixture
    train, held = split_events(frozen, 1)
    assert len(held) == round(len(frozen.first) / 3)
    assert split_events(frozen, 1) == (train, held)
    assert {row["id"] for row in train}.isdisjoint(row["id"] for row in held)
    assert len(train) + len(held) == len(frozen.first)


def test_less_than_six_events_has_no_holdout_gate(fixture: Fixture) -> None:
    cache, rows, _ = fixture
    frozen = session(cache, rows[:5], "insufficient-holdout")
    assert split_events(frozen, 1)[1] == []
    assert assess_statistics(frozen, cache)["holdout"]["supported"] is False


def test_cache_rejects_binary_dimension_and_rule_corruption(fixture: Fixture) -> None:
    cache, _, _ = fixture
    with pytest.raises(ValueError, match="binary"):
        replace(
            cache,
            values=tuple(
                tuple(tuple(2 for _ in cache.signal_ids) for _ in cache.candidate_ids)
                for _ in cache.years
            ),
        )
    with pytest.raises(ValueError, match="unique_candidates"):
        replace(cache, candidate_ids=("same", "same"))
    with pytest.raises(ValueError, match="cover_birth_plus_six"):
        replace(cache, years=cache.years[:-1])
    with pytest.raises(ValueError, match="rules_version"):
        replace(cache, rules_hash="wrong")


def test_scope_and_source_evidence_both_affect_cache_hash(fixture: Fixture) -> None:
    cache, _, frozen = fixture
    changed = replace(cache, scope=("other-owner", cache.scope[1], 1))
    assert changed.fingerprint != cache.fingerprint
    assert replace(cache, evidence_json='{"proof":"changed"}').fingerprint != (
        cache.fingerprint
    )
    with pytest.raises(ValueError, match="scope_or_years_mismatch"):
        assess_statistics(frozen, changed)


def test_event_mapping_is_explicitly_bazi_only_and_project_unreviewed() -> None:
    mappings = [item for rows in rules()["event_rules"].values() for item in rows]
    assert all(item["system"] == "bazi" for item in mappings)
    assert all(item["source"] is None for item in mappings)
    assert all("待审" in item["note"] for item in mappings)
