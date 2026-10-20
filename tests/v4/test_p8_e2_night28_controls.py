"""Cross-year relaxation is explicit; births/keys never enter public evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks.night28_audit import _rehearsal
from mingjing_core.adapters.charts.benchmarks.night28_controls import (
    SEED,
    no_chart_input,
    rehearse_controls,
    rehearse_no_chart,
    same_source_placebo,
)
from mingjing_core.adapters.charts.benchmarks.records import (
    BirthMetadata,
    Question,
    fingerprint,
)


def records(count: int = 3, source: str = "synthetic") -> list[Question]:
    return [
        Question(
            id=f"PRIVATE_ID_{index}_{source}",
            case_id=f"PRIVATE_CASE_{index}_{source}",
            text=f"请问{2010 + index}年会有哪项合成事件？PRIVATE_TEXT",
            options=tuple((letter, "PRIVATE_OPTION_" + letter) for letter in "ABCD"),
            answer="B",
            birth=BirthMetadata(
                1980 + index, 2, 3, 4, 5, "男", "PRIVATE_LOCATION", "solar"
            ),
            source=source,
            competition_year=2025,
        )
        for index in range(count)
    ]


def test_relaxation_crosses_target_years_without_changing_question_or_target():
    rows = records()
    changed = same_source_placebo(rows)
    assert len(changed) == len(rows)
    for original, placebo in zip(rows, changed, strict=True):
        assert original.birth != placebo.birth
        assert original.scoring_fingerprint() == placebo.scoring_fingerprint()
        assert replace(placebo, birth=original.birth) == original
    assert rows == records()
    report = rehearse_controls(rows)
    assert report["control_name"] == "宽松安慰剂（同源跨案例）"
    assert report["cross_target_year_allowed"] is True
    assert report["cross_source_allowed"] is False
    assert report["all_structural_checks_passed"] is True
    assert all(value == 3 for value in report["checks_passed"].values())
    assert report["placebo_inputs_built"] == report["no_chart_inputs_built"] == 3


def test_same_source_only_and_one_to_one_donors_across_multiple_questions():
    rows = records() + records(source="another_synthetic")
    rows.append(replace(rows[0], id="PRIVATE_NEXT", text="请问2024年会怎样？"))
    changed = same_source_placebo(rows)
    for source in ("synthetic", "another_synthetic"):
        selected = [row for row in rows if row.source == source]
        donor_births = {row.birth for row in selected}
        results = [row for row in changed if row.source == source]
        assert {row.birth for row in results} == donor_births
        assert len({row.case_id: row.birth for row in results}) == 3
    assert changed[0].birth == changed[-1].birth
    audit = rehearse_controls(rows)["pairs"]
    assert (
        audit[0]["donor_case_identity_sha256"]
        == audit[-1]["donor_case_identity_sha256"]
    )


def test_matching_is_reproducible_and_independent_of_input_order():
    rows = records(7)
    first = {row.id: row.birth for row in same_source_placebo(rows, 42)}
    reordered = {row.id: row.birth for row in same_source_placebo(rows[::-1], 42)}
    assert first == reordered
    assert rehearse_controls(rows, 42) == rehearse_controls(rows, 42)


@pytest.mark.parametrize("count", range(2, 20))
def test_every_case_has_distinct_birth_and_donor_reuse_is_a_permutation(count: int):
    rows = records(count)
    swapped = same_source_placebo(rows)
    assert {row.birth for row in swapped} == {row.birth for row in rows}
    assert all(a.birth != b.birth for a, b in zip(rows, swapped, strict=True))


@pytest.mark.parametrize("seed", [True, False, "20261020", None, 2.5])
def test_seed_is_an_explicit_integer(seed: Any):
    with pytest.raises(ValueError, match="integer_seed_required"):
        same_source_placebo(records(), seed)


@pytest.mark.parametrize("condition", ["singleton", "same_birth", "split_source"])
def test_impossible_complete_matching_does_not_silently_drop_cases(condition: str):
    rows = records(1 if condition == "singleton" else 2)
    if condition == "same_birth":
        rows[1] = replace(rows[1], birth=rows[0].birth)
    elif condition == "split_source":
        rows[1] = replace(rows[1], source="another_synthetic")
    with pytest.raises(
        ValueError, match="same_source_distinct_birth_matching_unavailable"
    ):
        same_source_placebo(rows)
    report = _rehearsal(rows)
    assert report["status"] == "unavailable"
    assert report["placebo_inputs_built"] == 0
    assert rehearse_no_chart(rows)["inputs_built"] == len(rows)


@pytest.mark.parametrize("condition", ["duplicate", "case_conflict", "no_year"])
def test_input_integrity_cannot_be_relaxed_with_year_matching(condition: str):
    rows = records()
    error = {
        "duplicate": "duplicate_question_identity",
        "case_conflict": "case_birth_conflict",
        "no_year": "explicit_question_year_required",
    }[condition]
    if condition == "duplicate":
        rows[1] = replace(rows[1], id=rows[0].id)
    elif condition == "case_conflict":
        rows[1] = replace(rows[1], case_id=rows[0].case_id)
    else:
        rows[0] = replace(rows[0], text="请问今年会怎样？")
    with pytest.raises(ValueError, match=error):
        same_source_placebo(rows)


def test_no_chart_only_has_original_question_and_permuted_options():
    row = records()[0]
    payload = no_chart_input(row)
    assert set(payload) == {"question", "options"}
    assert payload["question"] == row.text
    assert sorted(payload["options"].values()) == sorted(dict(row.options).values())
    assert "answer" not in payload and "birth" not in payload
    assert "question_id" not in payload and "chart" not in payload
    report = rehearse_no_chart([row])
    assert report["question_may_itself_contain_birth_hints"] is True
    assert report["inputs_built"] == 1 and report["inference_calls"] == 0


def test_public_rehearsal_contains_hashes_not_ids_text_birth_or_answers():
    rows = records()
    report = rehearse_controls(rows)
    encoded = json.dumps(report, ensure_ascii=False)
    for row in rows:
        for secret in (row.id, row.case_id, row.text, row.birth.location):
            assert secret not in encoded
        assert fingerprint(row.birth.public_input()) not in encoded
    assert "PRIVATE_" not in encoded
    assert report["professional_corpus_scores"] is None
    assert report["real_model_requests"] == report["inference_calls"] == 0
    assert report["chart_calculations"] == 0
    assert report["seed"] == SEED


def test_empty_batch_is_available_without_a_fabricated_score():
    assert same_source_placebo([]) == []
    report = rehearse_controls([])
    assert report["status"] == "no_eligible_questions"
    assert report["pairs"] == [] and report["questions"] == 0
    assert report["professional_corpus_scores"] is None
