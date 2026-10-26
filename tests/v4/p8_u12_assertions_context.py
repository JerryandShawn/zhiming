"""Synthetic handoff mutations test carrier integrity, not rule-computation validity."""

from __future__ import annotations

import json
from pathlib import Path

from mingjing_core.adapters.charts.benchmarks.handoff_refs import claim_id, document_id
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = json.loads(
    (ROOT / "mingjing_core/knowledge/p8_bazi/rules_v1.json").read_text(encoding="utf8")
)
RULES = REGISTRY["rules"]
TRUE_IDS = {
    "u12-pattern-hurting-officer-c3",
    "u12-pattern-indirect-seal-c1",
    "u12-pattern-indirect-seal-c3",
    "u12-pattern-killer-c3",
    "u12-pattern-officer-c3",
    "u12-pattern-output-c3",
    "u12-pattern-seal-c1",
    "u12-pattern-seal-c2",
    "u12-pattern-seal-c3",
}


def preview(system: str = "bazi") -> dict:
    return json.loads(
        (ROOT / f"docs/v4/contracts/samples/ayuan_{system}.json").read_text(
            encoding="utf8"
        )
    )


def native(chart: dict) -> dict:
    ref = chart["view"]["primary"][0]
    doc = next(
        row for row in chart["documents"] if row["document_id"] == ref["document_id"]
    )
    return pointer(doc["payload"], ref["path"])["p8"]


def root_alias(chart: dict) -> str:
    ref = chart["view"]["primary"][0]
    return next(row["alias"] for row in chart["aliases"]["c"] if row["ref"] == ref)


def rehash(chart: dict) -> None:
    mapping = {}
    for row in chart["documents"]:
        old = row["document_id"]
        row["document_id"] = document_id(
            chart["scope"], row["kind"], row["source_sha256"], row["payload"]
        )
        mapping[old] = row["document_id"]
    for refs in list(chart["view"].values()) + [chart.get("boundary_alerts", [])]:
        for ref in refs:
            ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
    documents = {row["document_id"]: row["payload"] for row in chart["documents"]}
    for rows in chart["aliases"].values():
        for row in rows:
            row["ref"]["document_id"] = mapping.get(
                row["ref"]["document_id"], row["ref"]["document_id"]
            )
            row["value_sha256"] = content_hash(
                pointer(documents[row["ref"]["document_id"]], row["ref"]["path"])
            )
            row["claim_id"] = claim_id(row)
