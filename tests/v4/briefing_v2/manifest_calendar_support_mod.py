"""Independent fictional host projections; no product manifest/evidence/hash helper determines truth."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.application.briefing_v2 import BasisRef, BriefItem, BriefSourceState, calendar_snapshot
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
TRANSIT = ROOT / "tests/v4/briefing_v2/fixtures/daily_transit_synthetic_20261021.json"
TEXTS = ROOT / "tools/eval/fixtures/mod_20261021/reflection_background_synthetic.json"
AT = datetime(2026, 10, 21, 7, tzinfo=ZoneInfo("Asia/Shanghai"))


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def raw_transit() -> dict[str, Any]:
    return json.loads(TRANSIT.read_text(encoding="utf-8"))


def fictional_text(index: int) -> str:
    rows = json.loads(TEXTS.read_text(encoding="utf-8"))["texts"]
    return rows["background" if index % 2 else "goal"]


def host_values(raw: dict[str, Any] | None = None, *, enabled: bool = True) -> dict[str, Any]:
    identity = raw_transit()["scope"]
    scope = FollowupScope(identity["owner_user_id"], identity["subject_id"])
    clock, subscription = FrozenClock(AT), BriefSubscription(scope, enabled=enabled)
    subscription_hash = digest({"enabled": enabled, "time": "07:00:00", "timezone": "Asia/Shanghai", "revision": 1})
    values = {
        "scope": scope,
        "subscription": subscription,
        "clock": clock,
        "calendar": calendar_snapshot(scope=scope, clock=clock),
        "settings": FollowupSettings(),
        "receptivity": ReceptivityState(scope.owner_id, scope.subject_id),
        "subscription_state": BriefSourceState("brief-subscription", scope, 1, subscription_hash),
    }
    if raw is not None:
        roots = {key: raw[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
        document_hash = digest(roots)
        assert raw["document_id"] == "tool-" + document_hash
        revision = raw["scope"]["revision"]
        values.update(
            transit=raw,
            profile_revision=revision,
            transit_state=BriefSourceState(raw["document_id"], scope, revision, document_hash),
        )
    return values


def notice(state: BriefSourceState, index: int, *, body: str | None = None) -> BriefItem:
    scope = state.scope
    at = AT + timedelta(hours=1, minutes=index)
    candidate = FollowupCandidate(
        f"synthetic-manifest-item-{index}",
        scope.owner_id,
        scope.subject_id,
        "reminder",
        at,
        explicit_requested=True,
        text=fictional_text(index) if body is None else body,
    )
    basis = BasisRef(
        f"m{100 + index}", state.source_id, state.revision, scope.owner_id, scope.subject_id, state.value_sha256
    )
    return BriefItem(
        DeliveryRequest(f"synthetic-manifest-occurrence-{index}", candidate, at), (basis,), "career", (state,)
    )
