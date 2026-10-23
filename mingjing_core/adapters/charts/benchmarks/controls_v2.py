"""Seeded option relabeling and within-competition-year case derangements."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any

from .eligibility_v2 import YearReview, question_year
from .records import Question, fingerprint


def shuffle_options(
    record: Question, seed: int, trial: int
) -> tuple[dict[str, Any], dict[str, str]]:
    order = list(record.options)
    random.Random(int(fingerprint([seed, record.id, trial])[:16], 16)).shuffle(order)
    mapping = {
        displayed: original
        for displayed, (original, _) in zip("ABCD", order, strict=True)
    }
    return {
        "question_id": record.id,
        "question": record.text,
        "options": {
            letter: text for letter, (_, text) in zip("ABCD", order, strict=True)
        },
    }, mapping


def _matching(cases: dict[str, Question], seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    sources, donors = sorted(cases), sorted(cases)
    rng.shuffle(sources)
    rng.shuffle(donors)
    adjacency = {
        ident: [
            donor
            for donor in donors
            if donor != ident and cases[donor].birth != cases[ident].birth
        ]
        for ident in sources
    }
    assigned: dict[str, str] = {}

    def augment(ident: str, seen: set[str]) -> bool:
        for donor in adjacency[ident]:
            if donor in seen:
                continue
            seen.add(donor)
            if donor not in assigned or augment(assigned[donor], seen):
                assigned[donor] = ident
                return True
        return False

    if not all(augment(ident, set()) for ident in sources):
        raise ValueError("same_year_distinct_birth_placebo_matching_unavailable")
    return {source: donor for donor, source in assigned.items()}


def _year(record: Question, basis: str, reviews: dict[str, YearReview]) -> int:
    year = (
        question_year(record, reviews.get(record.scoring_fingerprint())).year
        if basis == "question_year"
        else (record.birth.year if basis == "birth_year" else record.competition_year)
    )
    if year is None:
        raise ValueError(
            "placebo_explicit_question_year_missing"
            if basis == "question_year"
            else "placebo_year_value_missing"
        )
    return year


def same_year_placebo(
    records: list[Question],
    seed: int,
    *,
    year_basis: str,
    year_reviews: dict[str, YearReview] | None = None,
) -> list[Question]:
    if year_basis not in ("question_year", "birth_year", "competition_year"):
        raise ValueError("explicit_placebo_year_basis_required")
    groups: dict[tuple[str, int], dict[str, Question]] = {}
    case_years: dict[tuple[str, str], set[int]] = {}
    year_reviews = year_reviews or {}
    if set(year_reviews) - {row.scoring_fingerprint() for row in records}:
        raise ValueError("year_reviews_contain_unknown_questions")
    for record in records:
        year = _year(record, year_basis, year_reviews)
        case_years.setdefault((record.source, record.case_id), set()).add(year)
        group = groups.setdefault((record.source, year), {})
        if record.case_id in group and group[record.case_id].birth != record.birth:
            raise ValueError("placebo_case_birth_conflict")
        group[record.case_id] = record
    if any(len(years) != 1 for years in case_years.values()):
        raise ValueError("placebo_case_spans_question_years_cannot_preserve_one_donor")
    mappings = {
        key: _matching(cases, int(fingerprint([seed, key])[:16], 16))
        for key, cases in groups.items()
    }
    result = []
    for record in records:
        year = _year(record, year_basis, year_reviews)
        key = (record.source, year)
        result.append(
            replace(record, birth=groups[key][mappings[key][record.case_id]].birth)
        )
    return result
