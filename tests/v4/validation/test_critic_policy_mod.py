"""All item/confidence/calibration/revision-count combinations exercise program-owned verdicts."""

from __future__ import annotations

import json

import pytest

from mingjing_core.validation.calibration import (
    CalibrationIdentity,
    CalibrationProvenance,
    CalibrationReport,
    CalibrationSample,
    calculate_calibration,
)
from mingjing_core.validation.critic import compute_review, parse_attempts
from mingjing_core.validation.critic_contracts import (
    ITEM_TYPES,
    SEVERITIES,
    ProgramIssue,
)


@pytest.fixture(scope="module")
def hypothetical_calibration() -> CalibrationReport:
    ids = [f"synthetic-{i}" for i in range(60)]
    samples = [
        CalibrationSample(
            identity,
            {item: index % 2 == 0 for item in ITEM_TYPES},
            {item: index % 2 == 0 for item in ITEM_TYPES},
        )
        for index, identity in enumerate(ids)
    ]
    provenance = CalibrationProvenance(
        "synthetic-test-only", frozenset(ids), frozenset(ids[:15]), frozenset(ids[:10])
    )
    return calculate_calibration(
        samples,
        identity=CalibrationIdentity("synthetic-test-only", model="synthetic-primary"),
        provenance=provenance,
    )


def parsed_item(item: str, confidence: int = 3) -> object:
    raw = {
        "issues": [
            {
                "item": item,
                "type": ITEM_TYPES[item],
                "quote": "原句",
                "rule": "可观察标准",
                "evidence": "now" if item.startswith("E") else "",
                "fix_hint": "只改这一项",
                "confidence": confidence,
            }
        ]
    }
    return parse_attempts(
        [json.dumps(raw, ensure_ascii=False)], draft="合成原句", evidence_ids={"now"}
    )


@pytest.mark.parametrize("item", ITEM_TYPES)
@pytest.mark.parametrize("confidence", [1, 2, 3])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("used", [0, 1, 2])
def test_program_verdict_matrix(
    item: str,
    confidence: int,
    enabled: bool,
    used: int,
    hypothetical_calibration: CalibrationReport,
) -> None:
    review = compute_review(
        parsed_item(item, confidence),
        primary_model="synthetic-primary",
        calibration=hypothetical_calibration if enabled else None,
        revisions_used=used,
    )
    eligible = enabled and item not in {"J8", "J9"} and confidence >= 2 and used == 0
    assert review.verdict == ("revise" if eligible else "pass")
    assert review.issues[0].severity == SEVERITIES[item]
    assert review.issues[0].triggered == eligible
    assert len(review.sample_queue) == (1 if confidence == 1 else 0)
    expected_action = "revise" if eligible else "none"
    assert review.revision_action == expected_action


@pytest.mark.parametrize("item", ["E1", "E2", "E3", "E4", "E5"])
@pytest.mark.parametrize("used", [0, 1, 2, 99])
@pytest.mark.parametrize("allowed", [False, True])
def test_program_evidence_does_not_require_calibration_and_all_items_obey_revision_count(
    item: str, used: int, allowed: bool
) -> None:
    finding = ProgramIssue(item, "原句", "程序已核对", "program:1", "修正事实")
    review = compute_review(
        parse_attempts([], draft="原句", evidence_ids=set()),
        program_issues=(finding,),
        critic_allowed=allowed,
        revisions_used=used,
    )
    eligible = used == 0
    assert review.verdict == ("revise" if eligible else "pass")
    assert review.issues[0].source == "program" and review.issues[0].confidence == 3
    assert review.issues[0].triggered == eligible
    assert review.mode == ("full" if allowed else "evidence_only")


def test_low_confidence_issue_is_sampled_but_does_not_bypass_calibration_or_confidence(
    hypothetical_calibration: CalibrationReport,
) -> None:
    review = compute_review(
        parsed_item("E5", 1),
        primary_model="synthetic-primary",
        calibration=hypothetical_calibration,
        revisions_used=4,
    )
    assert review.verdict == "pass" and len(review.sample_queue) == 1
    assert review.issues[0].reason == "low_confidence"
    uncalibrated = compute_review(parsed_item("E5"), revisions_used=4)
    assert (
        uncalibrated.verdict == "pass"
        and uncalibrated.issues[0].reason == "record_only"
    )


def test_old_calibration_is_ignored_even_if_its_statistics_are_perfect(
    hypothetical_calibration: CalibrationReport,
) -> None:
    review = compute_review(
        parsed_item("E1"),
        primary_model="synthetic-primary",
        calibration=hypothetical_calibration,
        calibration_current=False,
    )
    assert review.verdict == "pass" and review.issues[0].reason == "record_only"


def test_no_quota_permission_drops_critic_issues_but_keeps_program_checks(
    hypothetical_calibration: CalibrationReport,
) -> None:
    review = compute_review(
        parsed_item("J1"),
        primary_model="synthetic-primary",
        calibration=hypothetical_calibration,
        critic_allowed=False,
        program_issues=(ProgramIssue("E1", "原句", "date", "now", "fix"),),
    )
    assert (
        review.mode == "evidence_only"
        and review.parse_attempts == 0
        and not review.parse_failed
    )
    assert [issue.item for issue in review.issues] == [
        "E1"
    ] and review.verdict == "revise"


def test_already_fixed_program_findings_record_without_revising_and_do_not_duplicate_model_findings(
    hypothetical_calibration: CalibrationReport,
) -> None:
    finding = ProgramIssue("E1", "原句", "weekday", "now", "fixed", resolved=True)
    review = compute_review(
        parsed_item("E1"),
        primary_model="synthetic-primary",
        calibration=hypothetical_calibration,
        program_issues=(finding,),
    )
    assert review.verdict == "pass" and len(review.issues) == 1
    assert review.issues[0].reason == "already_resolved"


def test_parser_failures_and_unavailable_provider_fail_open_with_metadata() -> None:
    failed = parse_attempts(
        ["first invalid", "second invalid"], draft="原文仍交付", evidence_ids=set()
    )
    result = compute_review(failed)
    assert (
        result.verdict == "pass" and result.parse_failed and result.parse_attempts == 2
    )
    assert result.issues == result.sample_queue == ()
    encoded = result.as_dict()
    assert (
        encoded["critic_prompt_version"] == "2.1.0"
        and encoded["calibration_version"] is None
    )
    assert not hasattr(result, "answer")


@pytest.mark.parametrize("used", [-1, True, 1.0, "1"])
def test_invalid_revision_counts_do_not_silently_enable_more_revisions(
    used: int,
) -> None:
    with pytest.raises(ValueError, match="revision count"):
        compute_review(
            parse_attempts([], draft="x", evidence_ids=set()), revisions_used=used
        )


def test_duplicate_program_items_are_not_counted_as_independent_evidence() -> None:
    finding = ProgramIssue("E1", "quote", "rule", "ref", "fix")
    with pytest.raises(ValueError, match="unique"):
        compute_review(
            parse_attempts([], draft="quote", evidence_ids=set()),
            program_issues=(finding, finding),
        )


def test_primary_model_change_or_missing_binding_keeps_old_calibration_record_only(
    hypothetical_calibration: CalibrationReport,
) -> None:
    for model in (None, "different-primary"):
        result = compute_review(
            parsed_item("E1"), calibration=hypothetical_calibration, primary_model=model
        )
        assert result.verdict == "pass" and result.issues[0].reason == "record_only"
    report = hypothetical_calibration
    assert report.state_for("E1") == "record_only"
    assert report.state_for("E1", primary_model="different-primary") == "record_only"
