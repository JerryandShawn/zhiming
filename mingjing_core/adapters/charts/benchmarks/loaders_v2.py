"""Per-question exclusions for current E2; historical strict loaders stay intact."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .eligibility_v2 import YearReview, select_questions
from .loaders import _birth, _options
from .records import Question, fingerprint


@dataclass(frozen=True)
class CorpusV2:
    records: tuple[Question, ...]
    report: dict[str, Any]


def _rows(data: Any, source: str, stem: str) -> tuple[list[dict[str, Any]], set[str]]:
    if source == "mingli":
        return [dict(row) for row in data["questions"]], {
            "mingli:" + row["case_id"] for row in data["questions"]
        }
    if source != "baziqa":
        raise ValueError("unknown_corpus_source")
    year = int(data[0]["current_year"]) if data and "contest_id" in data[0] else None
    rows, cases = [], set()
    for person in data:
        if "person_id" not in person:
            continue
        case = "baziqa:" + stem + ":" + person["person_id"]
        cases.add(case)
        for question in person["questions"]:
            rows.append(
                dict(question)
                | {"_profile": person["profile"], "_case": case, "_year": year}
            )
    return rows, cases


def _question(row: dict[str, Any], source: str) -> Question:
    if source == "mingli":
        if row.get("has_answer") is not True:
            raise ValueError("source_answer_unavailable")
        number = row.get("question_number")
        year = (
            2022 + (number - 1) // 40
            if type(number) is int and 1 <= number <= 160
            else None
        )
        fields = row["birth_info"]
        birth = _birth(fields, fields.get("gender"), fields.get("calendar_type"))
        ident, case, name = (
            "mingli:" + row["id"],
            "mingli:" + row["case_id"],
            "MingLi-Bench",
        )
    else:
        fields = row["_profile"]
        birth = _birth(
            fields["birth"],
            fields.get("gender"),
            fields["birth"].get("calendar", "solar"),
        )
        year, case, name = row["_year"], row["_case"], "BaziQA"
        ident = case + ":" + row["question_id"]
    return Question(
        id=ident,
        case_id=case,
        text=row["question"],
        options=_options(row["options"]),
        answer=row["answer"],
        birth=birth,
        source=name,
        category=row.get("category"),
        competition_year=year,
    )


def _schema_reason(exc: Exception) -> str:
    value = str(exc)
    if value in (
        "unrecognized_source_option",
        "expected_four_ordered_options",
        "option_text_missing",
    ):
        return "missing_or_invalid_option_labels"
    if value in ("answer_not_in_options", "source_answer_unavailable"):
        return "missing_or_invalid_answer_label"
    return "source_question_schema_invalid"


def _identity(row: dict[str, Any], source: str, index: int) -> str:
    return fingerprint(
        [
            source,
            row.get("_case", row.get("case_id")),
            row.get("id", row.get("question_id")),
            index,
        ]
    )


def _validated(
    rows: list[dict[str, Any]], source: str
) -> tuple[list[Question], list[dict[str, str]]]:
    parsed, excluded = [], []
    for index, row in enumerate(rows):
        try:
            parsed.append(_question(row, source))
        except (ValueError, KeyError, TypeError) as exc:
            excluded.append(
                {
                    "question_identity_sha256": _identity(row, source, index),
                    "reason": _schema_reason(exc),
                }
            )
    counts = Counter(row.id for row in parsed)
    births: dict[str, set[str]] = {}
    for row in parsed:
        births.setdefault(row.case_id, set()).add(fingerprint(row.birth.public_input()))
    valid = []
    for row in parsed:
        reason = "duplicate_question_identity" if counts[row.id] > 1 else None
        reason = reason or (
            "inconsistent_birth_for_source_case"
            if len(births[row.case_id]) > 1
            else None
        )
        if reason:
            excluded.append(
                {
                    "question_identity_sha256": fingerprint([row.source, row.id]),
                    "reason": reason,
                }
            )
        else:
            valid.append(row)
    return valid, excluded


def load_corpus_v2(
    path: Path,
    source: str,
    *,
    competition_year: int | None = None,
    reviews: dict[str, YearReview] | None = None,
) -> CorpusV2:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rows, source_cases = _rows(data, source, path.stem)
    valid, excluded = _validated(rows, source)
    schema_count = len(valid)
    selected = []
    for row in valid:
        if competition_year is not None and row.competition_year != competition_year:
            excluded.append(
                {
                    "question_identity_sha256": fingerprint([row.source, row.id]),
                    "reason": "outside_requested_contest_subset",
                }
            )
        else:
            selected.append(row)
    included, years = select_questions(selected, reviews=reviews)
    excluded += [
        {
            "question_identity_sha256": row["question_identity_sha256"],
            "reason": row["reason"],
        }
        for row in years["question_audit"]
        if not row["included"]
    ]
    report = _report(
        path,
        rows,
        source_cases,
        schema_count,
        included,
        excluded,
        years,
        competition_year,
    )
    return CorpusV2(tuple(included), report)


def _report(
    path: Path,
    rows: list[dict[str, Any]],
    source_cases: set[str],
    schema_count: int,
    included: list[Question],
    excluded: list[dict[str, str]],
    years: dict[str, Any],
    competition_year: int | None,
) -> dict[str, Any]:
    case_counts = Counter(row.case_id for row in included)
    source_case_counts = Counter(
        row.get("_case", "mingli:" + str(row.get("case_id"))) for row in rows
    )
    return {
        "contract": "e2-source-adjudication-v2",
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_questions": len(rows),
        "source_cases": len(source_cases),
        "source_case_question_count_distribution": dict(
            Counter(source_case_counts[case] for case in source_cases)
        ),
        "schema_valid_questions": schema_count,
        "included_questions": len(included),
        "included_cases": len(case_counts),
        "included_case_question_count_distribution": dict(
            Counter(case_counts.values())
        ),
        "excluded_questions": len(excluded),
        "excluded_reasons": dict(Counter(row["reason"] for row in excluded)),
        "excluded_audit": excluded,
        "question_year_adjudication": years,
        "requested_competition_year": competition_year,
        "competition_year_is_subset_filter_only": True,
        "source_content_redistributed": False,
        "scored": False,
        "real_model_requests": 0,
        "chart_preflight": "longitude_historical_offset_and_precision_required",
    }
