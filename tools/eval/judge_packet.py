"""Bound a private judge packet without inventing or rewriting its evidence."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

REFERENCE = Path(__file__).with_name("judge_reference_v1.md")
REFERENCE_IDS = {
    "time": ("REF-ZI-01", "REF-JQ-01", "REF-HOL-01"),
    "chart": ("REF-ZI-01", "REF-TST-01", "REF-JQ-01"),
    "safety": ("REF-SAFE-01", "REF-SAFE-02", "REF-PD"),
}


def serialized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def references(category: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    parts = re.split(r"^## (REF-[A-Z0-9-]+)\s*$", REFERENCE.read_text(encoding="utf-8"), flags=re.M)
    rules = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}
    ids = list(REFERENCE_IDS.get(category, ("REF-PD",)))
    selected = [{"id": ident, "text": rules[ident]} for ident in ids]
    if len(selected) > 3 or any(len(item["text"]) > 300 for item in selected):
        raise ValueError("judge_reference_budget_exceeded")
    return ids, selected, [rules["REF-PD"]]


def memories(seed: dict, evidence: dict, answer: str) -> list[dict]:
    """Merge fixture and observed IDs; a native tombstone always wins."""
    values: dict[str, dict] = {}
    bindings = evidence.get("seed_bindings", {})
    for index, item in enumerate(seed.get("facts", [])):
        label = item.get("id", "fact-" + str(index))
        ident = bindings.get(label, label)
        values[ident] = {
            "id": ident,
            "alias": label,
            "kind": item.get("kind", "fact"),
            "text": item.get("quote", item.get("content", item.get("summary", ""))),
            "source": "seed",
            "status": item.get("status", "active"),
        }
    for item in evidence.get("injected_facts", []):
        ident = item.get("id") or item.get("alias")
        if not ident:
            continue
        values[ident] = {**deepcopy(item), "source": "injected", "status": item.get("status", "active")}
    for item in evidence.get("memories", []):
        ident = item.get("id")
        if not ident:
            continue
        old = values.get(ident, {})
        values[ident] = {
            **old,
            "id": ident,
            "alias": old.get("alias", ident),
            "kind": item.get("kind", "fact"),
            "text": item.get("content") or item.get("summary") or old.get("text", ""),
            "source": old.get("source", "native"),
            "status": item.get("status", "active"),
        }
    for turn in evidence.get("prior_turns", []):
        for receipt in turn.get("receipts", []):
            if receipt.get("write_status") not in {"deleted", "stopped"}:
                continue
            ids = receipt.get("affected_ids", []) + [receipt.get("fact_id"), receipt.get("id")]
            for ident in ids:
                if ident in values:
                    values[ident]["status"] = "revoked@turn" + str(turn["turn"])
    return sorted(
        values.values(),
        key=lambda item: (
            not (item.get("alias") and "〔" + item["alias"] + "〕" in answer),
            item["source"] != "injected",
            not item["status"].startswith("revoked"),
        ),
    )


def bounded_packet(packet: dict) -> dict:
    packet = deepcopy(packet)
    packet["chart_claims"].sort(
        key=lambda item: not (item.get("alias") and "〔" + item["alias"] + "〕" in packet["answer"])
    )
    critical = {key: packet[key] for key in ("criterion", "product_decisions", "now", "seed_profile", "this_turn")}
    if len(serialized(critical)) > 2500 or len(packet["now"]) > 600:
        raise ValueError("judge_packet_required_budget_exceeded")
    truncation = {"memories_dropped": 0, "chart_claims_dropped": 0, "prior_turns_dropped": 0}
    for key, maximum in (("memories", 12), ("chart_claims", 10)):
        rows = packet[key]
        truncation[key + "_dropped"] = max(0, len(rows) - maximum)
        packet[key] = rows[:maximum]
        for row in packet[key]:
            text = row.get("text", "")
            if len(text) > 80:
                truncation[key + "_text_clipped"] = truncation.get(key + "_text_clipped", 0) + 1
                row["text"] = text[:80]
    for i, row in enumerate(packet["prior_turns"]):
        if i < len(packet["prior_turns"]) - 3:
            packet["prior_turns"][i] = {"turn": row["turn"], "effects": row.get("effects", [])}
            truncation["prior_turns_dropped"] += 1
        else:
            row["user_gist"] = row.get("user_gist", "")[:60]
    packet["truncation"] = truncation

    def measure():
        return len(serialized({key: value for key, value in packet.items() if key != "answer"}))

    # Evidence of deletion/cascades is never dropped to satisfy the budget.
    for key in ("memories", "chart_claims"):
        while measure() > 6000 and packet[key]:
            packet[key].pop()
            truncation[key + "_dropped"] += 1
    if measure() > 6000:
        raise ValueError("judge_packet_effects_budget_exceeded")
    packet["packet_chars"] = measure()
    packet["packet_sha256"] = hashlib.sha256(serialized(packet).encode("utf-8")).hexdigest()
    return packet
