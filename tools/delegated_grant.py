"""Read machine-issued v7 delegation receipts; never impersonate terminal consent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mingjing_core.models.quota_delegated import DEADLINE, token_parts
from mingjing_core.models.quota_runtime import CallScope
from mingjing_core.models.quota_types import GuardRejected, identifier, instant
from mingjing_core.timekit.clock import SystemClock


@dataclass(frozen=True)
class DelegatedGrant:
    batch_id: str
    authorization_id: str
    scenario_ids: tuple[str, ...]
    expires_at: datetime
    phase: str

    def scope(self, scenario_id: str) -> CallScope:
        if scenario_id not in self.scenario_ids:
            raise GuardRejected("batch_conflict")
        if SystemClock().now() >= self.expires_at:
            raise GuardRejected("authorization_expired")
        return CallScope(
            lane="probe" if self.phase == "equivalence" else "eval",
            batch_id=self.batch_id,
            authorization_id=self.authorization_id,
            scenario_id=scenario_id,
        )


def load_delegated_grant(path: Path) -> DelegatedGrant:
    try:
        if path.stat().st_size > 16384:
            raise ValueError("large receipt")
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value["schema"] != "member-delegated-start-v7"
            or type(value["model_calls"]) is not int
            or value["model_calls"] != 0
        ):
            raise ValueError("not a delegation receipt")
        parts = token_parts(value["authorization_id"])
        if parts is None or parts[0] != value["candidate_commit"]:
            raise ValueError("invalid delegation identity")
        phase = "equivalence" if parts[1] == "eq" else "core"
        if phase != value["phase"] or instant(datetime.fromisoformat(value["delegation_expires_at"])) != DEADLINE:
            raise ValueError("invalid delegation scope")
        scenarios = value["scenario_ids"]
        if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 10 or len(set(scenarios)) != len(scenarios):
            raise ValueError("invalid delegation scenarios")
        for scenario in scenarios:
            identifier(scenario)
        expires = instant(datetime.fromisoformat(value["expires_at"]))
        if not SystemClock().now() < expires <= DEADLINE:
            raise GuardRejected("authorization_expired")
        return DelegatedGrant(
            identifier(value["batch_id"]),
            identifier(value["authorization_id"]),
            tuple(scenarios),
            expires,
            phase,
        )
    except GuardRejected:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise GuardRejected("manual_start_required") from None
