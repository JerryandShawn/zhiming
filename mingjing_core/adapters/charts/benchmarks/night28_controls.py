"""Brain28 M2: seeded same-source case controls, with no inference transport."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .controls_v2 import _matching, shuffle_options
from .eligibility_v2 import question_year
from .records import Question, fingerprint

SEED = 20261020
CONTROL_NAME = "宽松安慰剂（同源跨案例）"


def _groups(records: list[Question]) -> dict[str, dict[str, Question]]:
    groups: dict[str, dict[str, Question]] = {}
    identities: set[tuple[str, str]] = set()
    for row in records:
        if question_year(row).year is None:
            raise ValueError("relaxed_placebo_explicit_question_year_required")
        if (row.source, row.id) in identities:
            raise ValueError("relaxed_placebo_duplicate_question_identity")
        identities.add((row.source, row.id))
        cases = groups.setdefault(row.source, {})
        if row.case_id in cases and cases[row.case_id].birth != row.birth:
            raise ValueError("relaxed_placebo_case_birth_conflict")
        cases[row.case_id] = row
    return groups


def _donors(
    groups: dict[str, dict[str, Question]], seed: int
) -> dict[str, dict[str, str]]:
    if type(seed) is not int:
        raise ValueError("relaxed_placebo_integer_seed_required")
    try:
        return {
            source: _matching(cases, int(fingerprint([seed, source])[:16], 16))
            for source, cases in groups.items()
        }
    except ValueError:
        raise ValueError("same_source_distinct_birth_matching_unavailable") from None


def same_source_placebo(records: list[Question], seed: int = SEED) -> list[Question]:
    """Swap only birth; all questions for a case share a distinct-source-case donor."""
    groups = _groups(records)
    donors = _donors(groups, seed)
    return [
        replace(row, birth=groups[row.source][donors[row.source][row.case_id]].birth)
        for row in records
    ]


def no_chart_input(record: Question, seed: int = SEED) -> dict[str, Any]:
    """Keep source question/options verbatim; omit IDs, metadata, charts and keys."""
    shuffled, _ = shuffle_options(record, seed, 0)
    return {key: shuffled[key] for key in ("question", "options")}


def rehearse_no_chart(records: list[Question], seed: int = SEED) -> dict[str, Any]:
    inputs = [no_chart_input(row, seed) for row in records]
    return {
        "name": "无盘对照",
        "status": "available" if records else "no_eligible_questions",
        "seed": seed,
        "inputs_built": len(inputs),
        "input_allowlist": ["question", "options"],
        "all_input_allowlists_valid": all(
            set(row) == {"question", "options"} for row in inputs
        ),
        "raw_source_ids_in_input": False,
        "question_prose_unchanged": True,
        "question_may_itself_contain_birth_hints": True,
        "structured_birth_or_derived_chart_provided": False,
        "professional_corpus_scores": None,
        "inference_calls": 0,
    }


def _pair_audit(records: list[Question], seed: int) -> list[dict[str, Any]]:
    groups = _groups(records)
    donors = _donors(groups, seed)
    years: dict[tuple[str, str], set[int | None]] = {}
    for row in records:
        years.setdefault((row.source, row.case_id), set()).add(question_year(row).year)
    return [
        {
            "source": row.source,
            "question_identity_sha256": fingerprint([row.source, row.id]),
            "case_identity_sha256": fingerprint([row.source, row.case_id]),
            "donor_case_identity_sha256": fingerprint(
                [row.source, donors[row.source][row.case_id]]
            ),
            "question_target_year": question_year(row).year,
            "donor_question_target_years": sorted(
                years[(row.source, donors[row.source][row.case_id])]
            ),
        }
        for row in records
    ]


def _checks(original: Question, swapped: Question, seed: int) -> dict[str, bool]:
    plain = no_chart_input(original, seed)
    placebo = no_chart_input(swapped, seed)
    _, labels = shuffle_options(original, seed, 0)
    return {
        "birth_changed": original.birth != swapped.birth,
        "question_unchanged": original.scoring_fingerprint()
        == swapped.scoring_fingerprint(),
        "target_year_unchanged": question_year(original) == question_year(swapped),
        "same_displayed_question": plain == placebo,
        "no_chart_allowlist": set(plain) == {"question", "options"},
        "answer_key_external": set(labels) == set("ABCD")
        and sorted(labels.values()) == list("ABCD"),
    }


def rehearse_controls(records: list[Question], seed: int = SEED) -> dict[str, Any]:
    """Actually construct paired inputs; structural checks are not task scores."""
    placebo = same_source_placebo(records, seed)
    checks = [_checks(a, b, seed) for a, b in zip(records, placebo, strict=True)]
    totals = {
        name: sum(row[name] for row in checks) for name in (checks[0] if checks else ())
    }
    return {
        "control_name": CONTROL_NAME,
        "status": "available" if records else "no_eligible_questions",
        "seed": seed,
        "year_basis": "question_explicit_target_year_unchanged",
        "donor_pool": "eligible_2025_competition_subset_same_source_cases",
        "cross_target_year_allowed": True,
        "cross_source_allowed": False,
        "same_case_donor_consistent": True,
        "distinct_birth_required": True,
        "matching": "seeded_one_to_one_case_derangement",
        "questions": len(records),
        "placebo_inputs_built": len(placebo),
        "no_chart_inputs_built": len(checks),
        "checks_passed": totals,
        "all_structural_checks_passed": all(all(row.values()) for row in checks),
        "pairs": _pair_audit(records, seed),
        "professional_corpus_scores": None,
        "real_model_requests": 0,
        "chart_calculations": 0,
        "inference_calls": 0,
    }
