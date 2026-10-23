"""Frozen first-release membership delegation gate, independent of request data."""

from __future__ import annotations

import re
from typing import Any

from .quota_types import GuardRejected

P3_IDS = frozenset(
    [f"T{i:02}" for i in range(1, 15)]
    + [f"M{i:02}" for i in (1, 2, 3, 4, 9, 10, 11, 13)]
    + [f"R{i:02}" for i in range(1, 10)]
    + [f"Q{i:02}" for i in range(1, 8)]
    + ["TA01", "TA02", "TA03", "D01", "S01", "X03a", "X03b", "X04", "X05", "L01"]
)
CORE_IDS = frozenset(
    [
        f"{prefix}{i:02}"
        for prefix, end in {
            "C": 7,
            "D": 2,
            "F": 4,
            "L": 2,
            "M": 13,
            "P": 7,
            "Q": 7,
            "R": 9,
            "S": 4,
            "T": 14,
            "TA": 3,
            "X": 8,
        }.items()
        for i in range(1, end + 1)
        if f"{prefix}{i:02}" != "X03"
    ]
    + ["X03a", "X03b"]
)
DATES_IDS = frozenset([f"DC{i:02}" for i in range(1, 5)] + [f"TR{i:02}" for i in range(1, 4)])
REQUIRED = {"p3": P3_IDS, "date_checks": DATES_IDS, "core": CORE_IDS}


def validate_gate(value: Any, candidate: str) -> None:
    if not isinstance(value, dict) or value.get("schema") != "first-release-scripted-gate-v1":
        raise GuardRejected("manual_start_required")
    if re.fullmatch(r"[0-9a-f]{40}", candidate) is None or value.get("candidate_commit") != candidate:
        raise GuardRejected("batch_conflict")
    if value.get("worktree_clean") is not True:
        raise GuardRejected("batch_conflict")
    source = value.get("source_sha256")
    if not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{64}", source) is None:
        raise GuardRejected("batch_conflict")
    for name, expected_ids in REQUIRED.items():
        result = value.get(name)
        if not isinstance(result, dict) or any(
            result.get(key) != expected
            for key, expected in {
                "mode": "scripted",
                "target": "v4",
                "status": "complete",
                "count": len(expected_ids),
                "passed": len(expected_ids),
                "candidate_commit": candidate,
                "source_sha256": source,
                "physical_requests": 0,
                "worktree_clean": True,
            }.items()
        ):
            raise GuardRejected("manual_start_required")
        if result.get("worktree_clean") is not True:
            raise GuardRejected("batch_conflict")
        identities = result.get("case_ids")
        if (
            not isinstance(identities, list)
            or any(not isinstance(item, str) for item in identities)
            or len(identities) != len(expected_ids)
            or set(identities) != expected_ids
            or any(type(result[key]) is not int for key in ("passed", "count", "physical_requests"))
        ):
            raise GuardRejected("batch_conflict")
