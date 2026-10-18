"""Read local official schemas without geocoding, API calls or data publication."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .records import BirthMetadata, Question


def _birth(fields: dict[str, Any], gender: Any, calendar: str | None) -> BirthMetadata:
    genders = {"男": "男", "女": "女", "male": "男", "female": "女"}
    if gender is not None and gender not in genders:
        raise ValueError("unrecognized_source_gender")
    return BirthMetadata(
        **{
            name: fields.get(name)
            for name in ("year", "month", "day", "hour", "minute")
        },
        gender=genders.get(gender),
        location=fields.get("location", fields.get("place")),
        calendar=calendar,
        approximate=fields.get("approximate"),
    )


def _options(values: list[Any]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for value in values:
        if isinstance(value, dict):
            result.append((value["letter"], value["text"]))
        elif isinstance(value, str) and (
            match := re.fullmatch(r"([ABCDabcd])[.．、:：\s]*(.+)", value.strip())
        ):
            # Official BaziQA mixes lowercase labels and labels without separators.
            result.append((match[1].upper(), match[2]))
        else:
            raise ValueError("unrecognized_source_option")
    return tuple(sorted(result))


def _unique(records: list[Question]) -> list[Question]:
    if not records or len({row.id for row in records}) != len(records):
        raise ValueError("empty_corpus_or_duplicate_question_ids")
    cases: dict[str, BirthMetadata] = {}
    for row in records:
        if row.case_id in cases and cases[row.case_id] != row.birth:
            raise ValueError("inconsistent_birth_for_source_case")
        cases[row.case_id] = row.birth
    return records


def load_mingli(path: Path) -> list[Question]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    records: list[Question] = []
    for row in data["questions"]:
        if row.get("has_answer") is not True:
            raise ValueError("source_answer_unavailable")
        number = row.get("question_number")
        year = (
            2022 + (number - 1) // 40
            if type(number) is int and 1 <= number <= 160
            else None
        )
        records.append(
            Question(
                id="mingli:" + row["id"],
                case_id="mingli:" + row["case_id"],
                text=row["question"],
                options=_options(row["options"]),
                answer=row["answer"],
                birth=_birth(
                    row["birth_info"],
                    row["birth_info"].get("gender"),
                    row["birth_info"].get("calendar_type"),
                ),
                source="MingLi-Bench",
                category=row.get("category"),
                competition_year=year,
            )
        )
    return _unique(records)


def load_baziqa(path: Path) -> list[Question]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    year = int(data[0]["current_year"]) if data and "contest_id" in data[0] else None
    records: list[Question] = []
    for row in data:
        if "person_id" not in row:
            continue
        profile = row["profile"]
        # Source docs call these Gregorian; preserve explicit exceptions.
        birth = _birth(
            profile["birth"],
            profile.get("gender"),
            profile["birth"].get("calendar", "solar"),
        )
        case_id = "baziqa:" + path.stem + ":" + row["person_id"]
        for question in row["questions"]:
            records.append(
                Question(
                    id=case_id + ":" + question["question_id"],
                    case_id=case_id,
                    text=question["question"],
                    options=_options(question["options"]),
                    answer=question["answer"],
                    birth=birth,
                    source="BaziQA",
                    category=question.get("category"),
                    competition_year=year,
                )
            )
    return _unique(records)


def inspect_corpus(path: Path, source: str) -> dict[str, Any]:
    if source not in ("mingli", "baziqa"):
        raise ValueError("unknown_corpus_source")
    summary: dict[str, Any] = {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_content_redistributed": False,
        "scored": False,
        "chart_preflight": "longitude_historical_offset_and_precision_required",
    }
    try:
        records = load_mingli(path) if source == "mingli" else load_baziqa(path)
    except (ValueError, KeyError, TypeError):
        # Fail closed at file level; no dropped questions or inferred option labels.
        return dict(
            summary,
            parse_status="blocked_source_schema_requires_review",
            questions=0,
            cases=0,
        )
    return dict(
        summary,
        **{
            "parse_status": "normalized",
            "questions": len(records),
            "cases": len({row.case_id for row in records}),
            "missing_birth_fields": {
                field: sum(getattr(row.birth, field) is None for row in records)
                for field in (
                    "year",
                    "month",
                    "day",
                    "hour",
                    "minute",
                    "gender",
                    "calendar",
                )
            },
        },
    )
