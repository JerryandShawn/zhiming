"""Read an already issued terminal receipt; loading never creates or renews authority."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

from mingjing_core.models.quota_runtime import CallScope, call_scope
from mingjing_core.models.quota_types import GuardRejected, identifier
from mingjing_core.timekit.clock import SystemClock


@dataclass(frozen=True)
class ManualGrant:
    suite: str
    batch_id: str
    authorization_id: str
    scenario_ids: tuple[str, ...]
    expires_at: datetime

    def scope(self, scenario_id: str) -> CallScope:
        if scenario_id not in self.scenario_ids:
            raise GuardRejected("batch_conflict")
        if SystemClock().now() >= self.expires_at:
            raise GuardRejected("authorization_expired")
        return CallScope(
            lane="probe" if self.suite == "PROBE" else "eval",
            run_id=self.batch_id,
            batch_id=self.batch_id,
            authorization_id=self.authorization_id,
            scenario_id=scenario_id,
        )


def load_manual_grant(path: Path, suite: str, scenario_ids: list[str] | tuple[str, ...]) -> ManualGrant:
    try:
        if path.stat().st_size > 16384:
            raise ValueError("receipt too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "schema",
            "suite",
            "batch_number",
            "batch_id",
            "authorization_id",
            "scenario_ids",
            "expires_at",
            "automatic_next_batch",
            "model_calls",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("invalid receipt envelope")
        if (
            value["schema"] != "member-manual-start-v1"
            or value["suite"] != suite
            or suite not in {"E1", "E2", "PROBE"}
            or value["automatic_next_batch"] is not False
            or type(value["model_calls"]) is not int
            or value["model_calls"] != 0
            or type(value["batch_number"]) is not int
            or not 1 <= value["batch_number"] <= 10000
        ):
            raise ValueError("invalid grant policy")
        scenarios = value["scenario_ids"]
        if (
            not isinstance(scenarios, list)
            or not 1 <= len(scenarios) <= 10
            or len(set(scenarios)) != len(scenarios)
            or not set(scenario_ids).issubset(scenarios)
        ):
            raise ValueError("invalid receipt scenarios")
        for scenario in scenarios:
            identifier(scenario)
        expires = datetime.fromisoformat(value["expires_at"])
        if expires.tzinfo is None or expires.utcoffset() is None or expires <= SystemClock().now():
            raise GuardRejected("authorization_expired")
        return ManualGrant(
            suite,
            identifier(value["batch_id"]),
            identifier(value["authorization_id"]),
            tuple(scenarios),
            expires.astimezone(UTC),
        )
    except GuardRejected:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise GuardRejected("manual_start_required") from None


@contextmanager
def evaluation_scope(scenario_id: str) -> Iterator[None]:
    # This is a reference to an existing PG grant, never an environment "yes".
    path = os.getenv("MEMBER_GRANT_RECEIPT")
    if path:
        suite = os.getenv("MEMBER_EVAL_SUITE", "E1")
        scope = load_manual_grant(Path(path), suite, [scenario_id]).scope(scenario_id)
    else:
        scope = CallScope(lane="eval", scenario_id=scenario_id)
    with call_scope(scope):
        yield


F = TypeVar("F", bound=Callable[..., Any])


def scoped_scenario(function: F) -> F:
    @wraps(function)
    def invoke(scenario: Any, *args: Any, **kwargs: Any) -> Any:
        with evaluation_scope(scenario.id):
            return function(scenario, *args, **kwargs)

    return invoke  # type: ignore[return-value]
