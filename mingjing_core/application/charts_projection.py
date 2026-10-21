"""Public diagnostics from trusted calculator/registry output, never engine stderr."""

from __future__ import annotations

import re
from typing import Any

SYSTEMS = {"bazi", "ziwei", "astro", "tarot"}
CODES = {
    "RULE_GAP",
    "unsupported",
    "UNSUPPORTED",
    "UNSUPPORTED_INFERENCE",
    "MISSING_INPUT",
    "REFERENCE_ERROR",
    "AUTH_SCOPE_ERROR",
    "SCOPE_MISMATCH",
    "STALE_INPUT",
    "DRAW_MISMATCH",
    "CALCULATION_ERROR",
}
REASONS = {
    "MISSING_INPUT": "本次计算缺少可用且已确认的出生参数，不能补出结果。",
    "AUTH_SCOPE_ERROR": "计算资料不属于本轮授权范围。",
    "RULE_GAP": "请求的计算能力尚未实现，不能补成支持。",
    "CALCULATION_ERROR": "本次计算未完成；未静默更换计算方法或出生参数。",
}


def public_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": error.get("code") if error.get("code") in REASONS else "CALCULATION_ERROR",
            "reason": REASONS.get(error.get("code"), REASONS["CALCULATION_ERROR"]),
            **({"system": error["system"]} if error.get("system") in SYSTEMS else {}),
        }
        for error in errors
        if isinstance(error, dict)
    ]


def coverage_gaps(computed: dict[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        status = gap.get("status") if gap.get("status") in CODES else "RULE_GAP"
        system = gap.get("system") or computed.get("artifacts", {}).get(gap.get("artifact_id"), {}).get("system")
        public = {"status": status}
        if system in SYSTEMS:
            public["system"] = system
        if isinstance(gap.get("rule_id"), str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,160}", gap["rule_id"]):
            public["rule_id"] = gap["rule_id"]
        # Registry reasons are trusted rule diagnostics, not arbitrary engine exceptions.
        if isinstance(gap.get("reason"), str):
            public["reason"] = gap["reason"][:600]
        public["issues"] = [
            {
                "code": issue.get("code") if issue.get("code") in CODES else "RULE_GAP",
                "detail": issue.get("detail", "")[:600],
            }
            for issue in gap.get("issues", [])
            if isinstance(issue, dict) and isinstance(issue.get("detail", ""), str)
        ]
        result.append(public)
    return result


def calculation_fallbacks(computed: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    methods = {"Moshier", "Swiss Ephemeris", "JPL", "unrecognized_ephemeris_flags"}
    bodies = {"太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"}
    for profile in computed.get("profiles", {}).values():
        for fallback in profile.get("fallback", []):
            if (
                not isinstance(fallback, dict)
                or fallback.get("requested") not in methods
                or fallback.get("actual") not in methods
            ):
                continue
            public = {"system": profile["system"], "requested": fallback["requested"], "actual": fallback["actual"]}
            if fallback.get("body") in bodies:
                public["body"] = fallback["body"]
            if fallback.get("layer") in ("natal", "transit_snapshot"):
                public["layer"] = fallback["layer"]
            if type(fallback.get("returned_flags")) is int:
                public["returned_flags"] = fallback["returned_flags"]
            result.append(public)
    return result


def chart_diagnostics(computed: dict[str, Any], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "coverage_gaps": coverage_gaps(computed, gaps),
        "calculation_errors": public_errors(computed["errors"]),
        "calculation_fallbacks": calculation_fallbacks(computed),
    }
