"""Independent synthetic host inputs and hash issuing; never uses the product evidence validator."""

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.application.briefing_v2 import (
    BasisRef,
    BriefItem,
    BriefSourceState,
    calendar_snapshot,
    subscription_basis,
)
from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.scheduling.brief_schedule import BriefSubscription
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/v4/briefing_v2/fixtures/daily_transit_synthetic_20261021.json"
MATRIX = ROOT / "docs/v4/evidence/MOD_2026-10-21/BRIEF_public_boundaries_frozen_matrix_20261021.json"
AT = datetime(2026, 10, 21, 7, tzinfo=ZoneInfo("Asia/Shanghai"))


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve(value: Any, path: str) -> Any:
    current = value
    for token in path[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if type(current) is list else current[key]
    return current


def reissue(raw: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(raw)
    document = "tool-" + digest({key: payload[key] for key in ("version", "scope", "data", "rule_hits", "sources")})
    hits = payload["rule_hits"] if type(payload["rule_hits"]) is list else []
    paths = sorted({path for hit in hits for path in hit["evidence_paths"]})
    charts = [claim(f"c{index}", path, resolve(payload, path), document) for index, path in enumerate(paths, 1)]
    names = {row["path"]: row["alias"] for row in charts}
    rules = []
    for index, hit in enumerate(hits, 1):
        row = claim(f"r{index}", f"/rule_hits/{index - 1}", hit, document)
        row.update(rule_id=hit["rule_id"], evidence_aliases=[names[path] for path in hit["evidence_paths"]])
        rules.append(row)
    payload.update(document_id=document, aliases={"c": charts, "r": rules})
    return payload


def claim(alias: str, path: str, value: Any, document: str) -> dict[str, str]:
    value_hash = digest(value)
    return {
        "alias": alias,
        "path": path,
        "value_sha256": value_hash,
        "claim_id": "claim-" + digest([document, path, value_hash]),
    }


def payload(kind: str = "all") -> dict[str, Any]:
    raw = json.loads(FIXTURE.read_bytes())
    predicates = {
        "ten_god": lambda c: c.get("system") == "bazi" and c.get("kind") == "ten_god" and c.get("layer") == "daily",
        "relation": lambda c: c.get("system") == "bazi"
        and c.get("kind") == "relation"
        and "daily" in c.get("target_layers", []),
        "ziwei": lambda c: c.get("system") == "ziwei" and c.get("kind") == "mutagen" and c.get("layer") == "daily",
        "astro": lambda c: c.get("system") == "astro" and c.get("kind") == "aspect",
    }
    kinds = ("ten_god", "ziwei", "astro") if kind == "all" else (kind,)
    raw["rule_hits"] = [next(hit for hit in raw["rule_hits"] if predicates[name](hit["context"])) for name in kinds]
    return reissue(raw)


def values(transit: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = json.loads(FIXTURE.read_bytes())["scope"]
    scope = FollowupScope(identity["owner_user_id"], identity["subject_id"])
    clock, subscription = FrozenClock(AT), BriefSubscription(scope)
    basis = subscription_basis(subscription)
    result = dict(
        scope=scope,
        subscription=subscription,
        clock=clock,
        calendar=calendar_snapshot(scope=scope, clock=clock),
        settings=FollowupSettings(),
        receptivity=ReceptivityState(scope.owner_id, scope.subject_id),
        subscription_state=BriefSourceState(basis.source_id, scope, basis.revision, basis.value_sha256),
    )
    if transit is not None:
        revision = transit["scope"]["revision"]
        result.update(
            transit=transit,
            profile_revision=revision,
            transit_state=BriefSourceState(transit["document_id"], scope, revision, transit["document_id"][5:]),
        )
    return result


def text(result: Any) -> str:
    return "\n".join(line.text for section in result.sections for line in section.lines)


def current_items(kind: str, scope: FollowupScope) -> tuple[BriefItem, ...]:
    fixture = ROOT / "tools/eval/fixtures/mod_20261021/reflection_background_synthetic.json"
    bodies = json.loads(fixture.read_bytes())["texts"]
    selected = (bodies["background"], bodies["goal"]) if kind == "BS01" else (bodies["background"],) * 2
    result = []
    for index, body in enumerate(selected, 1):
        revision = index if kind == "BS01" else 1
        value_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        candidate = FollowupCandidate(
            f"synthetic-current-{index}",
            scope.owner_id,
            scope.subject_id,
            "reminder",
            AT + timedelta(hours=index),
            explicit_requested=True,
            text=body,
        )
        basis = BasisRef(
            f"m{100 + index}", "synthetic-shared-source", revision, scope.owner_id, scope.subject_id, value_hash
        )
        state = BriefSourceState(basis.source_id, scope, revision, value_hash, revoked=kind == "BS02" and index == 2)
        result.append(
            BriefItem(
                DeliveryRequest(f"synthetic-current-occurrence-{index}", candidate, candidate.due_at),
                (basis,),
                "career",
                (state,),
            )
        )
    return tuple(result)
