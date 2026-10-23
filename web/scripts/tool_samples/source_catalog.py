"""Only reviewed school/source combinations can reach a public explanation."""

from __future__ import annotations

from .common import need, ref

CATALOG = {
    "window": {
        "catalog_id": "window-project-ranking-v1",
        "school": "project-cross-system-purpose-heuristic-not-a-traditional-election-school",
        "school_label": "项目跨体系用途排序（非传统择日流派）",
        "raw_source": "docs/v4/contracts/window_search.md",
        "source": {
            "title": "项目择日权重与条件契约",
            "url": "docs/v4/contracts/window_search.md",
            "status": "项目启发式；未验证预测效度",
        },
    },
    "bazi": {
        "catalog_id": "bazi-candidate-comparison-v1",
        "school": "ziping-structural-pairs-and-project-candidate-overlap-v1",
        "school_label": "子平结构与项目候选交集",
        "raw_source": {
            "title": "P8显式用神三候选与表层五行对读",
            "status": "project_descriptive_comparison_not_traditional_compatibility_algorithm",
        },
        "source": {
            "title": "P8显式用神三候选与表层五行对读",
            "status": "项目描述性对读；不是传统合婚算法",
        },
    },
    "astro": {
        "catalog_id": "astro-five-aspects-v1",
        "school": "tropical-geocentric-five-major-aspects-uniform-orb",
        "school_label": "热带地心五大相位（统一容许度）",
        "raw_source": "https://www.astro.com/swisseph/swephprg.htm",
        "source": {
            "title": "Swiss Ephemeris 官方接口",
            "url": "https://www.astro.com/swisseph/swephprg.htm",
            "status": "数值历表接口；不证明关系效度",
        },
    },
    "ziwei": {
        "catalog_id": "ziwei-side-by-side-v1",
        "school": "installed-py-iztro-natal-plus-project-side-by-side-v1",
        "school_label": "安装版紫微本命与项目并列对读",
        "raw_source": {
            "title": "iztro本命十二宫；跨盘并列为项目展示约定",
            "url": "https://docs.iztro.com/posts/astrolabe",
            "status": "installed_named_convention_not_independent_compatibility_validation",
        },
        "source": {
            "title": "iztro本命十二宫；跨盘并列为项目展示约定",
            "url": "https://docs.iztro.com/posts/astrolabe",
            "status": "安装版具名口径；非独立相容度验证",
        },
    },
}


def public_source(hit: dict) -> dict:
    rule = hit["rule_id"]
    family = "window" if rule.startswith("window.") else rule.split(".")[1]
    need(family in CATALOG)
    selected = CATALOG[family]
    need(hit["school"] == selected["school"] and hit["source"] == selected["raw_source"])
    return {
        "catalog_id": selected["catalog_id"],
        "school": selected["school"],
        "school_label": selected["school_label"],
        "source": dict(selected["source"]),
    }


def evidence(root: dict, summaries: dict[str, str]) -> list[dict]:
    result = []
    for alias in root["aliases"]["c"]:
        need(alias["path"] in summaries)
        result.append(
            {
                "ref": ref(root, alias["alias"]),
                "kind": "fact",
                "summary": summaries[alias["path"]],
                "value_sha256": alias["value_sha256"],
                "claim_id": alias["claim_id"],
            }
        )
    facts = {row["ref"]["alias"]: row["summary"] for row in result}
    for index, alias in enumerate(root["aliases"]["r"]):
        result.append(
            {
                "ref": ref(root, alias["alias"]),
                "kind": "rule",
                "summary": "已核对条件：" + facts[alias["evidence_aliases"][0]],
                "evidence_refs": [ref(root, name) for name in alias["evidence_aliases"]],
                "value_sha256": alias["value_sha256"],
                "claim_id": alias["claim_id"],
                **public_source(root["rule_hits"][index]),
            }
        )
    return result
