"""Compact native candidates, without current-turn evidence aliases or predictions."""

from __future__ import annotations


def profile_text(document: dict, revision: int) -> str | None:
    if type(revision) is not int or revision < 1:
        return None
    payload = document["payload"]
    if payload["time_basis"]["requires_confirmation"]:
        return None
    charts = [
        row
        for row in payload["charts"]
        if row.get("visible_by_default") is True and row["time_basis"]["basis"] == "true_solar"
    ]
    if len(charts) != 1:
        return None
    data = charts[0]["data"]["p8"]
    patterns, strength, useful = (data[name] for name in ("patterns", "strength", "useful_candidates"))
    names = [
        row["pattern"]
        for group in patterns.values()
        if isinstance(group, list)
        for row in group
        if isinstance(row, dict) and row.get("screen_passed") is True
    ]
    strong = "、".join(f"{row['conclusion']}[{row['method']}]" for row in strength["methods"])
    balancing = "/".join("".join(row["candidate_stems"]) for row in useful["balancing"])
    climate = "".join(useful["climate"]["candidate_stems"])
    pattern = "、".join(
        row["pattern"] + "：" + "".join(row["candidate_stems"])
        for row in useful["pattern"]
        if row["pattern_screen_passed"] is True
    )
    text = (
        f"命理档案v{revision}/{document['document_id']}，真太阳时/{data['school']}。"
        f"格局仅筛选候选：{'、'.join(dict.fromkeys(names)) or '未见通过'}[{patterns['method']}]；"
        f"旺衰：{strong}；喜用候选：扶抑{balancing}、调候{climate}、格局{pattern or '未见通过'}"
        f"[{useful['method']}]。项目诊断及摘表口径，分歧保留、非定论。"
        "这是历史档案，非本轮计算依据；要引用须本轮重新调用chart_compute。"
    )
    return text if len(text) <= 400 else None
