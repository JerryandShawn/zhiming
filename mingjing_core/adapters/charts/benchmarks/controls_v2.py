"""Seeded option relabeling and within-competition-year case derangements."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any

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


def same_year_placebo(
    records: list[Question], seed: int, *, year_basis: str
) -> list[Question]:
    if year_basis not in ("birth_year", "competition_year"):
        raise ValueError("explicit_placebo_year_basis_required")
    groups: dict[tuple[str, int], dict[str, Question]] = {}
    for record in records:
        year = (
            record.birth.year if year_basis == "birth_year" else record.competition_year
        )
        if year is None:
            raise ValueError("placebo_year_value_missing")
        group = groups.setdefault((record.source, year), {})
        if record.case_id in group and group[record.case_id].birth != record.birth:
            raise ValueError("placebo_case_birth_conflict")
        group[record.case_id] = record
    mappings = {
        key: _matching(cases, int(fingerprint([seed, key])[:16], 16))
        for key, cases in groups.items()
    }
    result = []
    for record in records:
        year = (
            record.birth.year if year_basis == "birth_year" else record.competition_year
        )
        key = (record.source, year)
        result.append(
            replace(record, birth=groups[key][mappings[key][record.case_id]].birth)
        )
    return result
