"""Pure critique parsing and revision planning; never retries a provider or edits an answer."""

from __future__ import annotations

import json
from collections.abc import Sequence, Set

from .calibration import CalibrationReport
from .critic_contracts import (
    CRITIC_PROMPT_VERSION,
    ITEM_TYPES,
    SEVERITIES,
    CriticIssue,
    CriticOutput,
    ParseResult,
    ProgramIssue,
    ReviewIssue,
    ReviewResult,
)
from .critic_request import build_critic_request as build_critic_request


class CriticParseError(ValueError):
    """A safe error code with no response text or validation-input diagnostics."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CriticParseError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise CriticParseError("non_json_number")


def parse_critic_output(raw: str, *, draft: str, evidence_ids: Set[str]) -> CriticOutput:
    if not isinstance(raw, str):
        raise CriticParseError("invalid_output_size")
    try:
        if len(raw.encode("utf-8")) > 262_144:
            raise CriticParseError("invalid_output_size")
        data = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
            raise CriticParseError("invalid_output_shape")
        data["issues"] = tuple(data["issues"])
        result = CriticOutput.model_validate(data)
    except CriticParseError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise CriticParseError("invalid_critic_output") from None
    for issue in result.issues:
        if issue.quote not in draft:
            raise CriticParseError("quote_not_in_draft")
        if issue.evidence and issue.evidence not in evidence_ids:
            raise CriticParseError("unknown_evidence_reference")
    return result


def parse_attempts(attempts: Sequence[str], *, draft: str, evidence_ids: Set[str]) -> ParseResult:
    if len(attempts) > 2:
        raise ValueError("at most two already-obtained critic outputs may be parsed")
    errors = []
    for index, raw in enumerate(attempts, start=1):
        try:
            return ParseResult(
                parse_critic_output(raw, draft=draft, evidence_ids=evidence_ids), index, False, tuple(errors)
            )
        except CriticParseError as error:
            errors.append(str(error))
    return ParseResult(CriticOutput(issues=()), len(attempts), True, tuple(errors) or ("critic_unavailable",))


def _review_issue(
    issue: CriticIssue | ProgramIssue,
    calibration: CalibrationReport | None,
    revisions_used: int,
    calibration_current: bool,
) -> ReviewIssue:
    program = isinstance(issue, ProgramIssue)
    confidence = 3 if program else issue.confidence
    severity = SEVERITIES[issue.item]
    state = calibration.state_for(issue.item) if calibration is not None and calibration_current else "record_only"
    reason = "eligible"
    if program and issue.resolved:
        reason = "already_resolved"
    elif confidence < 2:
        reason = "low_confidence"
    elif severity < 3:
        reason = "severity_below_revision_threshold"
    elif not program and state != "revision_enabled":
        reason = "record_only"
    elif revisions_used >= 1 and issue.item != "E6":
        reason = "revision_limit"
    return ReviewIssue(
        issue.item,
        ITEM_TYPES[issue.item],
        severity,
        confidence,
        issue.quote,
        issue.rule,
        issue.evidence,
        issue.fix_hint,
        "program" if program else "critic",
        reason == "eligible",
        reason,
    )


def compute_review(
    parsed: ParseResult,
    *,
    calibration: CalibrationReport | None = None,
    program_issues: Sequence[ProgramIssue] = (),
    critic_allowed: bool = True,
    revisions_used: int = 0,
    calibration_current: bool = True,
) -> ReviewResult:
    if type(revisions_used) is not int or revisions_used < 0:
        raise ValueError("revision count must be a nonnegative integer")
    if type(critic_allowed) is not bool or type(calibration_current) is not bool:
        raise ValueError("review gates must be booleans")
    if len({issue.item for issue in program_issues}) != len(program_issues):
        raise ValueError("program findings must be unique per rubric item")
    program_items = {issue.item for issue in program_issues}
    critic_issues = parsed.output.issues if critic_allowed else ()
    raw = tuple(program_issues) + tuple(issue for issue in critic_issues if issue.item not in program_items)
    issues = tuple(_review_issue(issue, calibration, revisions_used, calibration_current) for issue in raw)
    active = [issue for issue in issues if issue.triggered]
    action = "crisis" if any(issue.item == "E6" for issue in active) else "revise" if active else "none"
    return ReviewResult(
        "revise" if active else "pass",
        "full" if critic_allowed else "evidence_only",
        action,
        issues,
        tuple(issue for issue in issues if issue.confidence == 1),
        CRITIC_PROMPT_VERSION,
        calibration.identity.version if calibration else None,
        parsed.parse_failed if critic_allowed else False,
        parsed.attempts if critic_allowed else 0,
    )
