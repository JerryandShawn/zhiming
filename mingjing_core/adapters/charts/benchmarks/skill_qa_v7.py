"""Read-only chapter inventory and structural QA, not source authentication."""

from __future__ import annotations

import hashlib
import json

from mingjing_core.skills.loader import SkillLibrary

HEADINGS = (
    "方法步骤",
    "需要的盘面字段",
    "各流派观点与分歧",
    "适用前提",
    "反例与常见误读",
    "表达示例",
    "参考来源",
)


def inspect_chapter(loaded: dict) -> dict:
    """Structural presence is evidence of disclosure, never proof of factual accuracy."""
    metadata, text = loaded["metadata"], loaded["text"]
    issues = []
    for heading in HEADINGS:
        if f"## {heading}" not in text:
            issues.append("missing_heading:" + heading)
    for key in ("question_types", "required_fields", "artifact_root", "sources"):
        if not metadata.get(key):
            issues.append("missing_metadata:" + key)
    for index, source in enumerate(metadata.get("sources", [])):
        if not source.get("title") or not source.get("locator"):
            issues.append(f"source_locator_missing:{index}")
    if "存疑/待核" not in text:
        issues.append("pending_disclosure_missing")
    applicability = metadata.get("wiring_applicability", {})
    if applicability.get("enforcement_owner") != "mainline":
        issues.append("applicability_owner_missing")
    if "靠近交节 ±2 分钟" in text:
        issues.append("erratum_jie_boundary_2_minutes_vs_7200_seconds")
    return {
        "system": loaded["system"],
        "topic": loaded["topic"],
        "file": metadata["file"],
        "text_sha256_lf": loaded["sha256"],
        "metadata_sha256": hashlib.sha256(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "context_utf8_bytes": loaded["context_utf8_bytes"],
        "question_types": metadata.get("question_types", []),
        "artifact_root": metadata.get("artifact_root"),
        "required_fields": metadata.get("required_fields", []),
        "applicability": applicability,
        "sources": metadata.get("sources", []),
        "pending_fields": metadata.get("pending_fields", []),
        "issues": issues,
        "verification": "local_asset_review_not_original_edition_or_runtime_verification",
    }


def audit_library(library: SkillLibrary | None = None) -> dict:
    library = library or SkillLibrary()
    rows = [
        inspect_chapter(library.load(system, chapter["topic"]))
        for system in library.catalog["systems"]
        for chapter in library.chapters(system)
    ]
    return {
        "version": "p8-v7-skill-qa-v1",
        "catalog_version": library.catalog["version"],
        "systems": list(library.catalog["systems"]),
        "chapter_count": len(rows),
        "chapters": rows,
        "issues": [
            {"system": row["system"], "topic": row["topic"], "code": issue}
            for row in rows
            for issue in row["issues"]
        ],
        "effects": {"model_calls": 0, "business_writes": 0, "sends": 0},
    }
