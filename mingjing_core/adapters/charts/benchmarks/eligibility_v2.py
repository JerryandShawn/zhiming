"""Conservative question-year adjudication, independent of birth/contest metadata."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .records import Question, fingerprint

_YEAR = re.compile(r"(?<!\d)((?:1[6-9]|20|21)\d{2})\s*年")
_CLAUSE = re.compile(r"[^，,。！？?；;\n]+[！？?]?")
_BIRTH = re.compile(r"出生|生于|生於|诞生|誕生|生日|生辰")
_HISTORY = re.compile(r"已知|已于|已於|曾于|曾於|曾在|当时|當時|此前|过去|過去")
_TARGET = re.compile(
    r"请问|請問|[问問]|哪|是否|如何|可能|什么|甚麼|预测|預測|判断|判斷|将会|將會|会有|會有"
)
_RELATIVE = re.compile(
    r"今年|明年|去年|后年|後年|前年|最近|未来|未來|近[一二三四五六七八九十\d]+年"
)
_BIRTH_BEFORE = re.compile(
    r"(?:出生|生于|生於|诞生|誕生|生日|生辰)[于於时间時間日期为為：:在公历陽曆阳历\s]*$"
)
_BIRTH_AFTER = re.compile(
    r"^[\d\s月日号號时時分秒上午下午凌晨晚上:：/.-]{0,30}(?:出生|生人|诞生|誕生)"
)


@dataclass(frozen=True)
class YearReview:
    """A local reviewer identifies the exact target-year token in this question."""

    question_fingerprint: str
    year: int
    start: int
    end: int


@dataclass(frozen=True)
class YearDecision:
    year: int | None
    reason: str
    evidence_spans: tuple[tuple[int, int], ...] = ()

    @property
    def eligible(self) -> bool:
        return self.year is not None


def _is_birth_token(text: str, start: int, end: int) -> bool:
    return bool(
        _BIRTH_BEFORE.search(text[max(0, start - 16) : start])
        or _BIRTH_AFTER.search(text[end : end + 34])
    )


def _reviewed(record: Question, review: YearReview) -> YearDecision:
    if review.question_fingerprint != record.scoring_fingerprint():
        raise ValueError("year_review_question_fingerprint_mismatch")
    if (
        type(review.start) is not int
        or type(review.end) is not int
        or not 0 <= review.start < review.end <= len(record.text)
        or type(review.year) is not int
    ):
        raise ValueError("invalid_year_review_span")
    token = _YEAR.fullmatch(record.text[review.start : review.end])
    if token is None or int(token[1]) != review.year:
        raise ValueError("year_review_must_reference_explicit_question_year")
    if _is_birth_token(record.text, review.start, review.end):
        raise ValueError("year_review_cannot_use_birth_clause")
    return YearDecision(
        review.year, "reviewed_explicit_target_year", ((review.start, review.end),)
    )


def question_year(record: Question, review: YearReview | None = None) -> YearDecision:
    """Only explicit target clauses qualify; unidentified semantics stay excluded."""
    if review is not None:
        return _reviewed(record, review)
    targets: dict[int, list[tuple[int, int]]] = {}
    relative = False
    explicit = False
    for clause in _CLAUSE.finditer(record.text):
        text = clause.group()
        matches = list(_YEAR.finditer(text))
        explicit |= bool(matches)
        if _HISTORY.search(text):
            continue
        is_target = bool(_TARGET.search(text) or re.search(r"[？?]$", text))
        relative |= bool(is_target and _RELATIVE.search(text))
        if is_target:
            for match in matches:
                if _is_birth_token(text, match.start(), match.end()):
                    continue
                targets.setdefault(int(match[1]), []).append(
                    (clause.start() + match.start(), clause.start() + match.end())
                )
    if relative:
        return YearDecision(None, "ambiguous_relative_target_year")
    if len(targets) > 1:
        return YearDecision(None, "ambiguous_multiple_target_years")
    if targets:
        year = next(iter(targets))
        return YearDecision(year, "explicit_target_clause", tuple(targets[year]))
    return YearDecision(
        None,
        "explicit_year_target_unresolved" if explicit else "no_explicit_target_year",
    )


def select_questions(
    records: list[Question], *, reviews: dict[str, YearReview] | None = None
) -> tuple[list[Question], dict[str, Any]]:
    reviews = reviews or {}
    unknown = set(reviews) - {row.scoring_fingerprint() for row in records}
    if unknown:
        raise ValueError("year_reviews_contain_unknown_questions")
    included, audit = [], []
    for row in records:
        decision = question_year(row, reviews.get(row.scoring_fingerprint()))
        if decision.eligible:
            included.append(row)
        audit.append(
            {
                "question_identity_sha256": fingerprint([row.source, row.id]),
                "included": decision.eligible,
                "reason": decision.reason,
                "year_basis": "question_explicit_target_year"
                if decision.eligible
                else None,
                "evidence_spans": decision.evidence_spans,
            }
        )
    return included, {
        "policy": "brain23_question_year_v1",
        "source_questions": len(records),
        "included_questions": len(included),
        "excluded_questions": len(records) - len(included),
        "excluded_reasons": dict(
            Counter(row["reason"] for row in audit if not row["included"])
        ),
        "year_basis": "question_explicit_target_year",
        "metadata_year_fallback": False,
        "question_audit": audit,
    }
