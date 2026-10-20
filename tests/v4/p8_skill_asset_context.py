"""Offline skill audit helpers; no model, chart engine or database is started."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from hermes.tarot_deck import DECK_VERSION, MEANING_VERSION, SPREADS, card
from mingjing_core.adapters.charts.tool_evidence import pointer
from mingjing_core.adapters.tarot import TarotService

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "mingjing_core/skills"
CONTRACTS = ROOT / "docs/v4/contracts"


def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_asset_key")
        result[key] = value
    return result


def json_asset(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"), object_pairs_hook=unique_object)


def manifest(text: str) -> dict:
    """Validate only the project's two single-line keys, not arbitrary YAML."""
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError("local_manifest_delimiter_invalid")
    metadata = {}
    for line in lines[1 : lines.index("---", 1)]:
        match = re.fullmatch(r"(name|description): (\S.*)", line)
        if not match or match[1] in metadata:
            raise ValueError("local_manifest_metadata_invalid")
        metadata[match[1]] = match[2]
    if set(metadata) != {"name", "description"}:
        raise ValueError("local_manifest_metadata_invalid")
    return metadata


def groups(catalog: dict) -> dict:
    result = {}
    for system, package in catalog["systems"].items():
        for chapter in package["chapters"]:
            key = (system, chapter["topic"], "required_fields", "")
            result[key] = (chapter["artifact_root"], chapter["required_fields"])
            for item in chapter.get("conditional_fields", []):
                key = (
                    system,
                    chapter["topic"],
                    "conditional_fields",
                    item["capability"],
                )
                result[key] = (item["artifact_root"], item["paths"])
            for item in chapter.get("additional_interfaces", []):
                key = (system, chapter["topic"], "additional_interfaces", item["name"])
                result[key] = (item["root"], item["paths"])
    return result


def public_tarot_fixture() -> dict:
    """Reuse the existing revealed court-card fixture through the real serializer."""
    selected = {
        "position": 1,
        "label": SPREADS["focus1"]["positions"][0],
        "back_id": "opaque-synthetic-back",
        "revealed": True,
        "card_id": "cups-11",
        "orientation": "upright",
        "card_snapshot": card("cups-11"),
    }
    payload = {
        "question": "合成的行动反思",
        "spread": deepcopy(SPREADS["focus1"]),
        "deck_version": DECK_VERSION,
        "meaning_version": MEANING_VERSION,
        "draw_source": "auto",
        "reversals": True,
        "status": "ready",
        "context_snapshot": {},
        "selected": [selected],
        "revision": 1,
        "previous_draw_id": None,
    }
    row = {
        "id": "synthetic-draw",
        "subject": "synthetic-subject",
        "case_id": "case",
        "stage": "open",
        "payload": payload,
        "private_deck": [selected],
    }
    return TarotService(None)._viewer(row)


def source_root(source: dict) -> dict:
    if source["status"] != "available":
        raise ValueError("skill_root_unavailable")
    if source.get("factory") == "existing_public_tarot_fixture":
        return public_tarot_fixture()
    value = json_asset(CONTRACTS / source["sample"])
    if "document_kind" not in source:
        return value
    documents = [
        row
        for row in value["documents"]
        if row["kind"] == source["document_kind"]
        and (
            "technique" not in source
            or row["payload"].get("technique") == source["technique"]
        )
    ]
    if len(documents) != 1:
        raise ValueError("skill_sample_root_ambiguous")
    value = documents[0]["payload"]
    if source.get("select_artifact_system"):
        rows = [
            row
            for row in value["artifacts"].values()
            if row["system"] == source["select_artifact_system"]
        ]
        if len(rows) != 1:
            raise ValueError("skill_sample_artifact_ambiguous")
        value = rows[0]
    return value


def bindings(matrix: dict) -> dict:
    result = {}
    for row in matrix["chapters"]:
        key = (row["system"], row["topic"], "required_fields", "")
        result[key] = row["required_source"]
        for group, mapping in (
            ("conditional_fields", row.get("conditional_sources", {})),
            ("additional_interfaces", row.get("additional_sources", {})),
        ):
            for name, source_id in mapping.items():
                result[(row["system"], row["topic"], group, name)] = source_id
    return result


def resolved_values(root: dict, paths: list[str]) -> list:
    return [pointer(root, path) for path in paths]
