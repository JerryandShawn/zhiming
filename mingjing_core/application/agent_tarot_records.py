"""Body-free fixed-card artifacts and explicitly symbolic editorial claims."""

from __future__ import annotations

from typing import Any

from hermes.tarot_deck import DECK_VERSION, MEANING_VERSION, METHOD_VERSION, SPREADS, card
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint

METADATA = frozenset(
    {
        "id",
        "owner_user_id",
        "owner",
        "subject_id",
        "subject",
        "case_id",
        "revision",
        "status",
        "created_at",
        "updated_at",
    }
)


def verified_cards(draw: dict[str, Any]) -> list[dict[str, Any]]:
    if draw["status"] != "ready":
        return []
    if (draw["deck_version"], draw["meaning_version"], draw["method_version"]) != (
        DECK_VERSION,
        MEANING_VERSION,
        METHOD_VERSION,
    ):
        raise EvidenceError("塔罗牌面或牌义版本没有可复核的本机依据")
    spread = SPREADS.get(draw["spread"]["id"])
    if spread is None or fingerprint(draw["spread"]) != fingerprint(spread):
        raise EvidenceError("塔罗牌位与冻结版本不符")
    cards, seen = draw["cards"], set()
    if len(cards) != len(spread["positions"]):
        raise EvidenceError("固定塔罗牌数不完整")
    for position, item in enumerate(cards, 1):
        if (
            item["position"] != position
            or item["label"] != spread["positions"][position - 1]
            or item["revealed"] is not True
            or item["card_id"] in seen
            or item["orientation"] not in {"upright", "reversed"}
            or not draw["reversals"]
            and item["orientation"] != "upright"
        ):
            raise EvidenceError("固定塔罗牌位或方向不符")
        try:
            definition = card(item["card_id"])
        except ValueError:
            raise EvidenceError("固定塔罗牌不存在") from None
        if fingerprint(item["card"]) != fingerprint(definition):
            raise EvidenceError("塔罗牌义不是冻结原创版本")
        seen.add(item["card_id"])
    return cards


def record_payloads(run: dict[str, Any], cached: dict[str, Any], draw: dict[str, Any]) -> list[tuple[str, str, dict]]:
    cards = verified_cards(draw)
    if not cards:
        return []
    common = {
        "run_id": run["id"],
        "epoch": run["retry_epoch"],
        "basis": "fixed_tarot",
        "native_draw_id": draw["id"],
        "native_reading_id": cached["native_reading_id"],
        "source_ids": cached["source_ids"],
        "source_versions": cached["versions"],
        "source_ranges": [
            {key: ref[key] for key in ("message_id", "version", "start", "end")} for ref in cached["source_refs"]
        ],
    }
    artifact = {
        "draw_id": draw["id"],
        "reading": cached["reading"],
        "revision": draw["revision"],
        "deck_version": draw["deck_version"],
        "meaning_version": draw["meaning_version"],
        "method_version": draw["method_version"],
        "spread": draw["spread"],
        "draw_source": draw["draw_source"],
        "reversals": draw["reversals"],
        "question_sha256": fingerprint(draw["question"]),
        "options_sha256": fingerprint(draw["options"]),
        "native_case_id": draw["case_id"],
        "created_at": draw["created_at"],
        "updated_at": draw["updated_at"],
        "cards": [{key: item[key] for key in ("position", "label", "card_id", "orientation")} for item in cards],
    }
    rows = [("artifact", draw["id"], dict(common, artifact=artifact))]
    for item in cards:
        native = draw["id"] + ":position:" + str(item["position"])
        definition = item["card"]
        claim = {
            "claim_id": native,
            "artifact_id": draw["id"],
            "position": item["position"],
            "label": item["label"],
            "card_id": item["card_id"],
            "orientation": item["orientation"],
            "meaning_version": MEANING_VERSION,
            "text": definition[item["orientation"]],
            "misreading": definition["misreading"],
            "reflection_question": definition["question"],
            "source": definition["source"],
            "assertion_status": "symbolic_reflection",
            "not_user_fact": True,
        }
        rows.append(("interpretive_claim", native, dict(common, claim=claim)))
    return rows


def persist_records(service: Any, run: dict[str, Any], cached: dict[str, Any], draw: dict[str, Any]) -> list[dict]:
    records = []
    for kind, native, content in record_payloads(run, cached, draw):
        identity = [run["owner"], run["id"], run["retry_epoch"], kind, native, cached["native_reading_id"]]
        ident = "agent_tarot_" + kind + "_" + fingerprint(identity)[:32]
        operation = "tarot-proof:" + fingerprint(identity)
        row = service.repo.put(
            run["owner"], kind, ident, content, subject=run["subject"], expected_revision=0, operation_id=operation
        )
        if (
            row["status"] != "active"
            or row["subject_id"] != run["subject"]
            or row.get("case_id") is not None
            or row.get("run_id") != run["id"]
            or row.get("epoch") != run["retry_epoch"]
        ):
            raise ScopeError("塔罗专业记录不属于本轮有效人物")
        if fingerprint({key: value for key, value in row.items() if key not in METADATA}) != fingerprint(content):
            raise EvidenceError("塔罗专业记录已被改动")
        records.append(
            {
                "kind": kind,
                "id": row["id"],
                "revision": row["revision"],
                "native_id": native,
                "run_id": run["id"],
                "epoch": run["retry_epoch"],
                "basis": "fixed_tarot",
                "source_sha256": fingerprint(content),
            }
        )
    return records
