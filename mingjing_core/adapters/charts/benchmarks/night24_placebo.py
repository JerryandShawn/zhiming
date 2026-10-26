"""Metadata-only, one-attempt placebo feasibility report for the complete batch."""

from __future__ import annotations

from typing import Any

from .controls_v2 import same_year_placebo
from .eligibility_v2 import question_year
from .records import BirthMetadata, Question, fingerprint

SEED = 20261019
YEAR_BASIS = "question_year"
_SAFE_ERRORS = frozenset(
    {
        "placebo_explicit_question_year_missing",
        "placebo_case_birth_conflict",
        "placebo_case_spans_question_years_cannot_preserve_one_donor",
        "same_year_distinct_birth_placebo_matching_unavailable",
    }
)


def _structural_report(records: list[Question]) -> dict[str, Any]:
    groups: dict[tuple[str, int], dict[str, set[BirthMetadata]]] = {}
    case_years: dict[tuple[str, str], set[int]] = {}
    eligible = 0
    for record in records:
        year = question_year(record).year
        if year is None:
            continue
        eligible += 1
        case_years.setdefault((record.source, record.case_id), set()).add(year)
        group = groups.setdefault((record.source, year), {})
        group.setdefault(record.case_id, set()).add(record.birth)
    summaries = []
    for (source, year), cases in sorted(groups.items()):
        births = set().union(*cases.values())
        summaries.append(
            {
                "source": source,
                "target_year": year,
                "case_count": len(cases),
                "distinct_birth_count": len(births),
                "structurally_unmatchable": len(cases) < 2 or len(births) < 2,
            }
        )
    multi_year = [
        {
            "source": source,
            "case_identity_sha256": fingerprint([source, case_id]),
            "target_years": sorted(years),
        }
        for (source, case_id), years in sorted(case_years.items())
        if len(years) > 1
    ]
    return {
        "eligible_questions": eligible,
        "multi_year_case_count": len(multi_year),
        "multi_year_cases": multi_year,
        "group_count": len(summaries),
        "singleton_group_count": sum(row["case_count"] == 1 for row in summaries),
        "groups": summaries,
    }


def placebo_preflight(records: list[Question]) -> dict[str, Any]:
    """Try the declared batch once; never retry or weaken year/source matching."""
    report = {
        "seed": SEED,
        "year_basis": YEAR_BASIS,
        "actual_call_count": 1,
        "complete_batch_only": True,
        "retries": 0,
        "cross_source_fallback": False,
        "cross_year_fallback": False,
        "input_questions": len(records),
        **_structural_report(records),
    }
    try:
        placebo = same_year_placebo(records, SEED, year_basis=YEAR_BASIS)
    except Exception as error:
        # Unknown exceptions must not echo private IDs, question text or births.
        code = str(error) if type(error) is ValueError else ""
        report.update(
            status="unavailable",
            error_code=code if code in _SAFE_ERRORS else "e2_placebo_preflight_failed",
            placebo_questions=0,
            changed_births_count=0,
        )
        return report
    report.update(
        status="available" if records else "no_eligible_questions",
        error_code=None,
        placebo_questions=len(placebo),
        changed_births_count=sum(
            before.birth != after.birth
            for before, after in zip(records, placebo, strict=True)
        ),
    )
    return report
