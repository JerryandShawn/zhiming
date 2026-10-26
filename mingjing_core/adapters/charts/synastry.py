"""Consent-gated read-only comparison; never infers consent or relationship fate."""

from __future__ import annotations

from .astro_ephemeris import SWISS_SOURCE, aspects, finite
from .synastry_bazi import PROJECT_SOURCE, SOURCE, bazi_comparison, bazi_hits
from .synastry_ziwei import SOURCE as ZIWEI_SOURCE
from .synastry_ziwei import ziwei_comparison, ziwei_hits
from .tool_evidence import evidence_result

VERSION = "p8-synastry-v1"
KINDS = ("romantic", "friendship", "collaboration")


def _preflight(chart_a: dict, chart_b: dict, kind: str, consent: str | None) -> None:
    if consent != "user_confirmed":
        raise ValueError("CONSENT_REQUIRED：请先确认已获对方同意使用其出生资料")
    if kind not in KINDS:
        raise ValueError("synastry_kind_invalid")
    if not isinstance(chart_a, dict) or not isinstance(chart_b, dict):
        raise ValueError("synastry_input_invalid")
    if not chart_a.get("owner_user_id") or chart_a.get("owner_user_id") != chart_b.get(
        "owner_user_id"
    ):
        raise ValueError("AUTH_SCOPE_ERROR：两份资料须属当前已授权用户的计算范围")


def _astro(left: dict, right: dict, orb: float) -> tuple[dict, list[dict]]:
    data = {
        "positions_a": left,
        "positions_b": right,
        "orb_degrees": orb,
        "aspects": aspects(left, right, orb),
        "school": "tropical-geocentric-five-major-aspects-uniform-orb",
        "time_basis": "actual_UTC_not_true_solar",
    }
    hits = [
        {
            "rule_id": "synastry.astro." + row["aspect"],
            "met": True,
            "school": data["school"],
            "source": SWISS_SOURCE,
            "evidence_paths": [
                f"/data/astro/aspects/{index}",
                "/data/astro/orb_degrees",
                "/data/astro/positions_a/" + row["from"],
                "/data/astro/positions_b/" + row["to"],
            ],
        }
        for index, row in enumerate(data["aspects"])
    ]
    return data, hits


def _comparison_data(
    left, right, kind: str, as_of_date: str, orb: float
) -> tuple[dict, list[dict]]:
    bazi = bazi_comparison(left.bazi_data, right.bazi_data)
    ziwei = ziwei_comparison(left.ziwei_natal, right.ziwei_natal)
    astro, astro_hits = _astro(left.natal_planets, right.natal_planets, orb)
    astro["method"] = left.ephemeris.metadata()
    astro["natal_at_utc"] = {"a": left.candidate["utc"], "b": right.candidate["utc"]}
    data = {
        "kind": kind,
        "consent": "user_confirmed",
        "as_of_date": as_of_date,
        "bazi": bazi,
        "astro": astro,
        "ziwei": ziwei,
        "methods": {
            "a": left.candidate["pillar_method"],
            "b": right.candidate["pillar_method"],
        },
        "time_basis": {
            "a": {"primary": left.candidate, "comparisons": left.basis_comparisons},
            "b": {"primary": right.candidate, "comparisons": right.basis_comparisons},
        },
    }
    return data, bazi_hits(bazi) + astro_hits + ziwei_hits(ziwei)


def synastry(
    chart_a: dict,
    chart_b: dict,
    kind: str,
    *,
    consent: str | None,
    as_of_date: str,
    orb_degrees: float = 6.0,
) -> dict:
    _preflight(chart_a, chart_b, kind, consent)
    from .daily_transit_natal import prepare_natal, validate_natal

    orb = finite(orb_degrees, 0, 10)
    validate_natal(chart_a, as_of_date)
    validate_natal(chart_b, as_of_date)
    left, right = prepare_natal(chart_a, as_of_date), prepare_natal(chart_b, as_of_date)
    data, hits = _comparison_data(left, right, kind, as_of_date, orb)
    scope = {
        "owner_user_id": chart_a["owner_user_id"],
        "subject_ids": [chart_a["subject_id"], chart_b["subject_id"]],
        "revisions": [chart_a["revision"], chart_b["revision"]],
        "operation_ids": [chart_a["operation_id"], chart_b["operation_id"]],
    }
    result = evidence_result(
        VERSION,
        data,
        hits,
        [SOURCE, PROJECT_SOURCE, ZIWEI_SOURCE, {"url": SWISS_SOURCE}],
        scope,
    )
    result["limits"] += [
        "consent是调用方明确确认字段，不能替代主线真实授权与撤销检查；不发送或保存对方资料。",
        "同一结构可用于讨论相处方式，不表示婚配概率、人格结论或关系成败。",
        "五行缺项不等于用神；扶抑/调候/格局候选分别列出，力量与合化未判。",
    ]
    return result
