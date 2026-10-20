"""Synthetic next-trigger and claim-time decision observations, without actual scheduling."""

import argparse
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.followups_contracts import (  # noqa: E402
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest  # noqa: E402
from mingjing_core.scheduling.delivery_rules import plan_delivery  # noqa: E402
from mingjing_core.scheduling.recurrence import next_trigger  # noqa: E402
from mingjing_core.scheduling.recurrence_contracts import RecurrenceRule  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 17, tzinfo=UTC)


def recurrence_workload() -> int:
    rules = (
        RecurrenceRule("daily", time(9)),
        RecurrenceRule("workday", time(9)),
        RecurrenceRule("lunar_monthly", time(9), day=1),
    )
    for index in range(120):
        result = next_trigger(rules[index % 3], AT)
        assert result.at > AT and not result.needs_clarification
    return 120


def delivery_workload() -> int:
    scope, clock = FollowupScope("synthetic", "self"), FrozenClock(AT)
    due = AT - timedelta(minutes=30)
    candidate = FollowupCandidate("reminder", "synthetic", "self", "reminder", due, explicit_requested=True)
    request = DeliveryRequest("occurrence", candidate, due)
    settings, state = FollowupSettings(), ReceptivityState("synthetic", "self")
    for _ in range(1000):
        result = plan_delivery(request, settings, state, scope=scope, clock=clock)
        assert result.allowed and result.original_due == due and result.late_minutes == 30
    return 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [
        measure("p7_120_mixed_next_triggers", recurrence_workload),
        measure("p7_1000_delivery_plans", delivery_workload),
    ]
    sources = [*Path("mingjing_core/scheduling").glob("*.py"), Path(__file__)]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(result["name"], "median_seconds", result["median_seconds"])


if __name__ == "__main__":
    main()
