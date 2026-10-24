"""R11 release-scope evidence is separate from the original all-81 gate."""

from __future__ import annotations

import re
from typing import Any

from .quota_gate import CORE_IDS, DATES_IDS, P3_IDS
from .quota_types import GuardRejected

DEFERRED_IDS = frozenset({"L02", "M08", "X01", "X02", "X06", "X08", *[f"P{i:02}" for i in range(1, 7)]})
CORE30_IDS = frozenset(
    [
        "T05",
        "T08",
        "T09",
        "T10",
        "T14",
        "TM01",
        "M01",
        "M03",
        "M05",
        "R02",
        "R07",
        "F01",
        "Q01",
        "Q02",
        "Q03",
        "Q04",
        "Q05",
        "D01",
        "S02",
        "S03",
        "S04",
        "C04",
        "AX01",
        "C01",
        "C02",
        "C03",
        "C05",
        "C07",
        "TA01",
    ]
)
REQUIRED = {
    "p3": P3_IDS,
    "date_checks": DATES_IDS,
    "core": CORE_IDS - DEFERRED_IDS,
    "core30": CORE30_IDS,
}


def _require(condition: object) -> None:
    if not condition:
        raise GuardRejected("manual_start_required")


def validate_r11(value: Any, candidate: str) -> None:
    _require(isinstance(value, dict) and value.get("schema") == "first-release-scripted-gate-r11")
    _require(re.fullmatch(r"[0-9a-f]{40}", candidate) and value.get("candidate_commit") == candidate)
    _require(value.get("worktree_clean") is True and value.get("equivalent") is None)
    source = value.get("source_sha256")
    _require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{64}", source))
    _require(type(value.get("original_core_count")) is int and value["original_core_count"] == 81)
    deferred = value.get("deferred")
    _require(isinstance(deferred, dict) and set(deferred) == DEFERRED_IDS)
    _require(all(isinstance(reason, str) and reason.strip() for reason in deferred.values()))
    for name, expected in REQUIRED.items():
        group = value.get(name)
        _require(isinstance(group, dict))
        _require(
            all(
                group.get(key) == expected_value
                for key, expected_value in {
                    "mode": "scripted",
                    "target": "v4",
                    "status": "complete",
                    "candidate_commit": candidate,
                    "source_sha256": source,
                    "count": len(expected),
                    "passed": len(expected),
                    "physical_requests": 0,
                }.items()
            )
        )
        _require(group.get("worktree_clean") is True)
        _require(all(type(group[key]) is int for key in ("count", "passed", "physical_requests")))
        identities = group.get("case_ids")
        _require(isinstance(identities, list) and all(isinstance(item, str) for item in identities))
        _require(len(identities) == len(expected) and set(identities) == expected)
        _require(group.get("raw_report_status") in ({"complete", "incomplete"} if name == "core" else {"complete"}))
    x02 = value.get("x02_equivalent")
    _require(isinstance(x02, dict))
    _require(x02.get("id") == "X02-r11" and x02.get("status") == "passed")
    _require(x02.get("friendly_failure") is True and x02.get("committed_answer_preserved") is True)
    for key, expected in {
        "score": 1,
        "mock_http_requests": 4,
        "repeat_writes": 0,
        "external_provider_requests": 0,
    }.items():
        _require(type(x02.get(key)) is int and x02[key] == expected)
    contract = x02.get("original_contract_sha256")
    _require(isinstance(contract, str) and re.fullmatch(r"[0-9a-f]{64}", contract))


def validate_raw_reports(value: dict, reports: dict[str, dict]) -> None:
    """Do not authorize from derived counts while the original reports disagree."""
    validate_r11(value, value.get("candidate_commit", ""))
    _require(set(reports) == set(REQUIRED))
    for name, expected in REQUIRED.items():
        report = reports[name]
        _require(isinstance(report, dict))
        meta, cases = report.get("metadata"), report.get("cases")
        _require(isinstance(meta, dict) and isinstance(cases, list))
        _require(all(isinstance(row, dict) for row in cases))
        for key in ("mode", "target", "candidate_commit", "source_sha256"):
            _require(meta.get(key) == value[name][key])
        _require(meta.get("worktree_clean") is True and not meta.get("stop_reason"))
        _require(type(meta.get("external_provider_requests")) is int and meta["external_provider_requests"] == 0)
        _require(meta.get("status") == value[name]["raw_report_status"])
        identities = [row.get("id") for row in cases]
        all_ids = CORE_IDS if name == "core" else expected
        _require(all(isinstance(identity, str) for identity in identities))
        _require(len(identities) == len(all_ids) and set(identities) == all_ids)
        for row in cases:
            _require(row.get("status") in {"passed", "failed"})
            evidence = row.get("v4_evidence")
            _require(isinstance(evidence, dict) and type(evidence.get("external_provider_requests")) is int)
            _require(evidence["external_provider_requests"] == 0)
            if row["id"] in expected:
                _require(row["status"] == "passed" and type(row.get("score")) in {int, float} and row["score"] == 1)
