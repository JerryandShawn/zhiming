"""Hash-only review of existing local E2 caches; no chart/model transport."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .eligibility_v2 import question_year
from .loaders_v2 import _identity, _question, _rows, _validated, load_corpus_v2
from .records import Question, fingerprint

COMPETITION_YEAR = 2025


def _contest_year(row: dict[str, Any], source: str) -> int | None:
    if source == "baziqa":
        return row.get("_year")
    number = row.get("question_number")
    return (
        2022 + (number - 1) // 40
        if type(number) is int and 1 <= number <= 160
        else None
    )


def _included_row(record: Question) -> dict[str, Any]:
    decision = question_year(record)
    return {
        "source": record.source,
        "question_identity_sha256": fingerprint([record.source, record.id]),
        "case_identity_sha256": fingerprint([record.source, record.case_id]),
        "competition_year": record.competition_year,
        "question_target_year": decision.year,
        "year_basis": "question_explicit_target_year",
        "reason": decision.reason,
        "evidence_spans": [list(pair) for pair in decision.evidence_spans],
    }


def _subset_exclusions(
    rows: list[dict[str, Any]], source: str, full: dict[str, Any]
) -> list[dict[str, Any]]:
    reasons = {
        row["question_identity_sha256"]: row["reason"] for row in full["excluded_audit"]
    }
    years = {
        row["question_identity_sha256"]: row
        for row in full["question_year_adjudication"]["question_audit"]
    }
    output = []
    for index, row in enumerate(rows):
        if _contest_year(row, source) != COMPETITION_YEAR:
            continue
        try:
            record = _question(row, source)
            ident = fingerprint([record.source, record.id])
        except (ValueError, KeyError, TypeError):
            ident = _identity(row, source, index)
        if ident in reasons:
            output.append(
                {
                    "source": {"mingli": "MingLi-Bench", "baziqa": "BaziQA"}[source],
                    "question_identity_sha256": ident,
                    "reason": reasons[ident],
                    "year_basis": None,
                    "evidence_spans": [
                        list(pair)
                        for pair in years.get(ident, {}).get("evidence_spans", [])
                    ],
                }
            )
    return output


def _audit_file(path: Path, source: str) -> tuple[dict[str, Any], list[Question]]:
    source_bytes = path.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    data = json.loads(source_bytes.decode("utf-8-sig"))
    raw_rows, _ = _rows(data, source, path.stem)
    subset = [row for row in raw_rows if _contest_year(row, source) == COMPETITION_YEAR]
    full = load_corpus_v2(path, source).report
    official = load_corpus_v2(path, source, competition_year=COMPETITION_YEAR)
    included = list(official.records)
    valid, _ = _validated(raw_rows, source)
    excluded = _subset_exclusions(raw_rows, source, full)
    if (
        digest != full["sha256"]
        or digest != official.report["sha256"]
        or digest != hashlib.sha256(path.read_bytes()).hexdigest()
    ):
        raise ValueError("source_changed_during_audit")
    if len(subset) != len(included) + len(excluded):
        raise ValueError("source_eligibility_audit_mismatch")
    return {
        "file": path.name
        if re.fullmatch(r"data\.json|contest8_\d{4}\.json", path.name)
        else "redacted_local_source_filename",
        "source_file_sha256": digest,
        "full_source_questions": len(raw_rows),
        "full_source_cases": full["source_cases"],
        "full_schema_valid_questions": full["schema_valid_questions"],
        "full_included_questions": full["included_questions"],
        "full_excluded_questions": full["excluded_questions"],
        "full_excluded_reasons": full["excluded_reasons"],
        "subset_source_questions": len(subset),
        "subset_source_cases": len(
            {row.get("_case", row.get("case_id")) for row in subset}
        ),
        "subset_schema_valid_questions": sum(
            row.competition_year == COMPETITION_YEAR for row in valid
        ),
        "subset_included_questions": len(included),
        "subset_excluded_questions": len(excluded),
        "outside_2025_rows": len(raw_rows) - len(subset),
        "unresolved_contest_year_rows": sum(
            _contest_year(row, source) is None for row in raw_rows
        ),
        "subset_excluded_reasons": dict(Counter(row["reason"] for row in excluded)),
        "included_audit": [_included_row(row) for row in included],
        "excluded_audit": excluded,
    }, included


def _source_summary(
    source: str, commit: str, files: list[dict[str, Any]]
) -> dict[str, Any]:
    counts = (
        "full_source_questions",
        "full_source_cases",
        "full_schema_valid_questions",
        "full_included_questions",
        "full_excluded_questions",
        "subset_source_questions",
        "subset_source_cases",
        "subset_schema_valid_questions",
        "subset_included_questions",
        "subset_excluded_questions",
        "outside_2025_rows",
        "unresolved_contest_year_rows",
    )
    reasons: Counter[str] = Counter()
    for row in files:
        reasons.update(row["subset_excluded_reasons"])
    return {
        "source": source,
        "source_commit": commit,
        "source_commit_scope": "local_repository_HEAD_not_clean_file_attestation",
        **{key: sum(row[key] for row in files) for key in counts},
        "subset_excluded_reasons": dict(reasons),
        "files": files,
    }


def audit_source(root: Path, source: str) -> tuple[dict[str, Any], list[Question]]:
    """Discard source exception details, which can contain personal source IDs."""
    try:
        if source not in ("mingli", "baziqa"):
            raise ValueError("unknown_source")
        paths = (
            [root / "data/data.json"]
            if source == "mingli"
            else sorted((root / "data").glob("contest8_*.json"))
        )
        if not paths:
            raise ValueError("local_cache_missing")
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise ValueError("invalid_local_source_commit")
        files, records = [], []
        for path in paths:
            report, selected = _audit_file(path, source)
            files.append(report)
            records.extend(selected)
        return _source_summary(source, commit, files), records
    except Exception:
        raise ValueError("e2_local_source_audit_failed") from None
