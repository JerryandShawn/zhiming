"""New reports keep machine evidence while uncalibrated judge-only failures wait."""

from copy import deepcopy


def mark_brain_review(case, calibration=None):
    if case.get("stop_reason") or case.get("target_error_code") or case.get("error_code"):
        return case
    failures = case.get("failed_assertions", [])
    judge_failures = [name for name in failures if name.endswith((".judge_score", ".judge_error"))]
    hard = [name for name in failures if name not in judge_failures]
    literal = all(
        any(token in name for token in (".must_include_all", ".must_include_any", ".must_not_include")) for name in hard
    )
    if hard and not literal:
        return case
    entries = case.get("private_evidence", [])
    details = []
    for entry in entries:
        value = entry.get("judge") or {}
        details.append(value.get("details") or value)
    severe = [issue for value in details for issue in value.get("issues", []) if issue.get("severity", 0) >= 3]
    human = any(value.get("needs_human") for value in details)
    scores = [entry.get("judge_score", entry.get("score")) for entry in entries]
    if hard and not (
        scores and all(score is not None and score >= 0.8 for score in scores) and not severe and not human
    ):
        return case
    if not hard and not (judge_failures or human or case.get("judge_unavailable")):
        return case
    calibrated = calibration or {}
    if (
        severe
        and not human
        and all(
            calibrated.get(issue["type"], {}).get("state") == "revision_enabled"
            and calibrated[issue["type"]].get("kappa", 0) >= 0.6
            for issue in severe
        )
    ):
        return case
    case.setdefault("machine_status", case["status"])
    case.setdefault("machine_score", case.get("score"))
    case["needs_brain_review"] = True
    case["review_reason"] = "literal_suspect" if hard else "judge_only_uncalibrated"
    case["review_failed_assertions"] = deepcopy(failures)
    if case["status"] != "incomplete" or case.get("scenario_complete"):
        case["status"] = "needs_brain_review"
    return case
