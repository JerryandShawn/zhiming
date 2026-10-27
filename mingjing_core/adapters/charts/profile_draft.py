"""U3 read-only versioned calculation judgments for a future profile service."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .adapter import stable_id


def profile_proposal(
    calculation: dict[str, Any],
    owner: str,
    subject: str,
    revision: int,
    *,
    previous_version: str | None = None,
    change_reason: str | None = None,
) -> dict[str, Any]:
    if previous_version and (not isinstance(change_reason, str) or not change_reason.strip()):
        raise ValueError("改判必须提供理由，不能静默替换档案")
    if calculation.get("errors") or not calculation.get("artifacts"):
        raise ValueError("有计算错误或缺少产物，不能生成核心判断档案")
    branches = []
    for artifact in calculation["artifacts"].values():
        if (artifact.get("owner_user_id"), artifact.get("subject_id"), artifact.get("revision")) != (
            owner,
            subject,
            revision,
        ):
            raise ValueError("档案来源归属或资料版本不匹配")
        if artifact["system"] != "bazi" or "p8" not in artifact["data"]:
            continue
        profile = calculation["profiles"][artifact["profile_id"]]
        if (profile["owner_user_id"], profile["subject_id"], profile["revision"]) != (owner, subject, revision):
            raise ValueError("档案口径归属或资料版本不匹配")
        p8 = artifact["data"]["p8"]
        judgments = [
            {
                "topic": topic,
                "artifact_id": artifact["id"],
                "path": "/data/p8/" + key,
                "value": deepcopy(p8[key]),
                "actual_method": deepcopy(profile["actual_method"]),
            }
            for topic, key in (("格局候选", "patterns"), ("旺衰", "strength"), ("喜用候选", "useful_candidates"))
        ]
        branches.append({"branch_id": artifact["branch_id"], "judgments": judgments})
    if not branches:
        raise ValueError("缺少具名P8八字计算，不以旧启发式冒充命理档案")
    payload = {
        "schema": "p8-metaphysics-profile-proposal-v1",
        "owner_user_id": owner,
        "subject_id": subject,
        "revision": revision,
        "previous_version": previous_version,
        "change_reason": change_reason,
        "branches": branches,
        "status": "calculation_proposal_not_persisted",
        "writes": 0,
        "limits": ["多个时间分支与流派判断并列保留；候选不是事实，档案持久化/版本更正由主线服务负责。"],
    }
    return dict(payload, version_id=stable_id("metaphysics-profile-", payload))
