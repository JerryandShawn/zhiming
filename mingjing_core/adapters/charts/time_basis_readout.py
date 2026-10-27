"""Choose a declared interpretation basis without selecting a physical fold."""

from __future__ import annotations

from typing import Any

from .p8_policy import release_policy


def rebase_column_evidence(column: dict[str, Any], prefix: str) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if (
                    key.endswith("_pointer")
                    and isinstance(item, str)
                    and item.startswith("/data/")
                ):
                    value[key] = prefix + item[len("/data") :]
                elif key == "evidence_paths":
                    value[key] = [
                        prefix + path[len("/data") :]
                        if path.startswith("/data/")
                        else path
                        for path in item
                    ]
                else:
                    visit(item)

    flying = column["p8_flying_transformations"]
    visit(flying)
    flying["evidence_document_root"] = "complete_time_basis_response"
    flying["evidence_data_root"] = prefix


def _differences(primary: dict[str, Any], comparison: dict[str, Any]) -> list[str]:
    fields = [
        "bazi.pillars." + key
        for key in ("year", "month", "day", "hour")
        if primary["data"]["pillars"][key] != comparison["data"]["pillars"][key]
    ]
    for key in ("palaces", "ming_gong", "shen_gong", "lunar_date", "wuxing_ju"):
        if primary["ziwei_column"].get(key) != comparison["ziwei_column"].get(key):
            fields.append("ziwei." + key)
    return fields


def _beijing_text(chart: dict[str, Any]) -> str:
    pillars = chart["data"]["pillars"]
    values = "、".join(
        pillars[key]["ganzhi"] for key in ("year", "month", "day", "hour")
    )
    ziwei = chart["ziwei_column"]
    return f"按北京时间则为四柱{values}；紫微命宫{ziwei['ming_gong']}、身宫{ziwei['shen_gong']}。"


def attach_readout(
    result: dict[str, Any], charts: list[dict[str, Any]]
) -> dict[str, Any]:
    primary = [row for row in charts if row["time_basis"]["basis"] == "true_solar"]
    beijing = {
        row["time_basis"]["instant_id"]: row
        for row in charts
        if row["time_basis"]["basis"] == "beijing_standard"
    }
    comparisons, visible_ids = [], set()
    for row in primary:
        other = beijing[row["time_basis"]["instant_id"]]
        differences = _differences(row, other)
        if differences:
            visible_ids.add(other["id"])
            comparisons.append(
                {
                    "primary_chart_id": row["id"],
                    "comparison_chart_id": other["id"],
                    "fields_changed": differences,
                    "text": _beijing_text(other),
                }
            )
    for row in charts:
        basis = row["time_basis"]["basis"]
        row["interpretation_role"] = (
            "primary"
            if basis == "true_solar"
            else "comparison"
            if row["id"] in visible_ids
            else "diagnostic"
        )
        row["visible_by_default"] = basis == "true_solar" or row["id"] in visible_ids
    # A school decision does not resolve a duplicated or nonexistent civil time.
    result["selected_basis"] = "true_solar" if primary else None
    result["requires_confirmation"] = any(
        row["requires_confirmation"] for row in result["instants"]
    )
    result["limits"] = [
        "真太阳时为默认解读口径；北京时间UTC+8结果不同时并列，当地标准时保留供核对。",
        "口径选择不消除夏令时重复/不存在时刻；没有确认出生资料或写入档案。",
    ]
    return {
        "version": "p8-time-basis-readout-23-v1",
        **release_policy()["interpretation"],
        "primary_chart_ids": [row["id"] for row in primary],
        "comparisons": comparisons,
        "physical_instant_confirmation_required": result["requires_confirmation"],
    }
