"""Pure, evidence-bound Chinese wording; conversation deduplication belongs to Core."""

from __future__ import annotations

import math
import re
from typing import Any

from mingjing_core.adapters.charts.tool_evidence import pointer

LABELS = {
    "hour_branch": "时辰交界",
    "late_zi_day": "晚子23点换日交界",
    "zi_midnight": "子夜0点流派交界",
    "jie_month": "节气交接",
    "eot_implementations": "两种均时差实现的差异",
}
PILLARS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}


def _evidence(document: dict, rule: dict, evidence: list[dict]) -> dict:
    if not isinstance(rule, dict) or not re.fullmatch(
        r"r[1-9][0-9]*", str(rule.get("alias", ""))
    ):
        raise ValueError("boundary_alias_invalid")
    alert = pointer(document, rule.get("path"))
    if (
        not isinstance(alert, dict)
        or alert.get("met") is not True
        or alert.get("critical") is not True
    ):
        raise ValueError("boundary_not_a_true_critical_hit")
    paths = alert.get("evidence_paths", [])
    expected = rule.get("evidence_aliases", [])
    if not paths or not expected or len(expected) != len(set(expected)):
        raise ValueError("boundary_evidence_missing")
    selected = [row for row in evidence if row.get("alias") in expected]
    if (
        len(selected) != len(expected)
        or {row["alias"] for row in selected} != set(expected)
        or {row["path"] for row in selected} != set(paths)
    ):
        raise ValueError("boundary_evidence_mismatch")
    for row in selected:
        if not re.fullmatch(r"c[1-9][0-9]*", str(row.get("alias", ""))):
            raise ValueError("boundary_alias_invalid")
        pointer(document, row["path"])
    return alert


def _comparison(alert: dict) -> tuple[list[str], str]:
    current = alert.get("current_pillars")
    if not isinstance(current, dict) or any(
        not isinstance(current.get(key), str) for key in PILLARS
    ):
        raise ValueError("boundary_pillars_missing")
    rows = [
        row
        for row in alert.get("alternatives", [])
        if isinstance(row.get("pillars"), dict)
    ]
    if not rows:
        raise ValueError("boundary_alternatives_missing")
    changed = [
        key
        for key in PILLARS
        if any(row["pillars"].get(key) != current[key] for row in rows)
    ]
    phrases = []
    for key in changed:
        values = []
        for row in rows:
            value = row["pillars"].get(key)
            if not isinstance(value, str) or not row.get("school"):
                raise ValueError("boundary_comparison_incomplete")
            values.append(f"{row.get('label', '对照')}：{value}（{row['school']}）")
        phrases.append(
            f"{PILLARS[key]}当前为{current[key]}，对照为" + "；".join(values)
        )
    return changed, "。".join(
        phrases
    ) if phrases else "现有对照未出现四柱差异，保留默认口径"


def render_boundary(
    document: dict[str, Any],
    rule: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    brief: bool = False,
) -> dict[str, Any]:
    """Use server-registered aliases relative to this verified document only.

    The caller verifies owner/revision/provenance before calling and decides whether
    the same profile revision has already had its full explanation this session.
    """
    alert = _evidence(document, rule, evidence)
    kind = alert.get("boundary_kind")
    if kind not in LABELS or not alert.get("school") or not alert.get("source"):
        raise ValueError("boundary_kind_or_source_invalid")
    distance = alert.get("distance_seconds")
    if (
        type(distance) not in (int, float)
        or not math.isfinite(distance)
        or distance < 0
    ):
        raise ValueError("boundary_distance_invalid")
    changed, comparison = _comparison(alert)
    refs = "".join(f"〔{name}〕" for name in [*rule["evidence_aliases"], rule["alias"]])
    if brief:
        text = f"这里沿用本次资料版本前面说明的{LABELS[kind]}口径。{refs}"
    else:
        measure = "实现差值" if kind == "eot_implementations" else "离交界的距离"
        text = (
            f"这里有个小边界：{LABELS[kind]}，{measure}是{distance:.3f}秒。"
            f"{comparison}。当前按{alert['school']}解读。"
            f"这些是核对用的对照，不是新的出生事实；先保留你的记录，不据此改档或倒推时辰。{refs}"
        )
    return {
        "text": text,
        "boundary_kind": kind,
        "affected_pillars": changed,
        "school": alert["school"],
        "source": alert["source"],
        "rule_alias": rule["alias"],
        "evidence_aliases": list(rule["evidence_aliases"]),
        "profile_update_allowed": False,
        "state_writes": 0,
    }
