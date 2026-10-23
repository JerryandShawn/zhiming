"""Deterministic public decision cards; free text cannot assert enum certainty."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from mingjing_core.agent.event_contracts import Options
from mingjing_core.agent.tools.interaction_parameters import PresentOptions
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.validation.structural import SAVE_CLAIM, StructuralResult, check_structure

CARD_FIELDS = ("title", "benefit", "cost", "risk", "first_step")


def project_options(run: dict[str, Any], seq: int, values: Any) -> dict[str, Any]:
    try:
        raw = PresentOptions.model_validate({"options": values}).model_dump()["options"]
        identity = json.dumps([run["id"], run["retry_epoch"], seq], separators=(",", ":"))
        ident = "options-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        decisions = []
        for index, item in enumerate(raw):
            fields = {key: item[key].strip() for key in CARD_FIELDS}
            if any(not value for value in fields.values()):
                raise ValueError("empty decision field")
            reversible = item["reversibility"]
            decisions.append(
                dict(
                    fields,
                    id=f"{ident}-{index + 1}",
                    reversibility=reversible if reversible in {"easy", "partial", "hard", "unknown"} else "unknown",
                    unknowns=[],
                )
            )
        return Options.model_validate({"options_id": ident, "prompt": None, "options": decisions}).model_dump()
    except (ValidationError, TypeError, ValueError):
        raise EvidenceError("真实决策步骤的卡片结构无效") from None


def options_text(options: dict[str, Any] | None) -> str:
    return json.dumps(options, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if options else ""


def review_material(text: str, options: dict[str, Any] | None) -> str:
    return text + "\n\n" + options_text(options) if options else text


def merge_card_structure(
    checked: StructuralResult,
    options: dict[str, Any] | None,
    aliases: dict[str, dict[str, Any]],
    receipts: tuple[dict[str, Any], ...],
) -> StructuralResult:
    if options is None:
        return checked
    facts, claims, keys = list(checked.used_fact_ids), list(checked.used_claim_ids), list(checked.cited_keys)
    for item in options["options"]:
        for field in CARD_FIELDS:
            text = item[field]
            plain = check_structure(text, aliases)
            # A receipt only supports the entity actually cited in this field.
            exact = tuple(
                row
                for row in receipts
                if row.get("write_status") == "saved"
                and row.get("kind", "") + ":" + str(row.get("id", row.get("fact_id"))) in plain.cited_keys
            )
            result = check_structure(text, aliases, exact)
            if result.text != text or SAVE_CLAIM.search(text) and not exact:
                raise EvidenceError("决策卡片含无效引用或缺少对应的真实保存回执")
            facts.extend(result.used_fact_ids)
            claims.extend(result.used_claim_ids)
            keys.extend(result.cited_keys)
    return replace(
        checked,
        used_fact_ids=tuple(dict.fromkeys(facts)),
        used_claim_ids=tuple(dict.fromkeys(claims)),
        cited_keys=tuple(dict.fromkeys(keys)),
    )
