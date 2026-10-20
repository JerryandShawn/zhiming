"""Complete briefing composition with a published synthetic P8 snapshot and current host doubles."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.briefing_v2 import (  # noqa: E402
    BasisRef,
    BriefItem,
    BriefSourceState,
    calendar_snapshot,
    compose_briefing,
    subscription_basis,
)
from mingjing_core.application.followups_contracts import (  # noqa: E402
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.scheduling.brief_schedule import BriefSubscription  # noqa: E402
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

FIXTURE = ROOT / "tests/v4/briefing_v2/fixtures/daily_transit_synthetic_20261021.json"
AT = datetime(2026, 10, 21, 7, tzinfo=ZoneInfo("Asia/Shanghai"))


def item(index: int, scope: FollowupScope, *, due: datetime, area: str) -> BriefItem:
    body = f"SYNTHETIC_BRIEF_ITEM_{index}"
    digest = hashlib.sha256(body.encode()).hexdigest()
    ref = BasisRef(f"m{index}", f"synthetic-source-{index}", 1, scope.owner_id, scope.subject_id, digest)
    candidate = FollowupCandidate(
        f"synthetic-notice-{index}",
        scope.owner_id,
        scope.subject_id,
        "reminder",
        due,
        explicit_requested=True,
        text=body,
    )
    request = DeliveryRequest(f"synthetic-occurrence-{index}", candidate, due)
    state = BriefSourceState(ref.source_id, scope, ref.revision, ref.value_sha256)
    return BriefItem(request, (ref,), area, (state,))


def arguments(payload: dict) -> dict:
    scope = FollowupScope(payload["scope"]["owner_user_id"], payload["scope"]["subject_id"])
    if not scope.owner_id.startswith("synthetic-") or not scope.subject_id.startswith("synthetic-"):
        raise ValueError("benchmark_requires_explicit_synthetic_scope")
    subscription = BriefSubscription(scope)
    basis, clock = subscription_basis(subscription), FrozenClock(AT)
    return {
        "scope": scope,
        "subscription": subscription,
        "settings": FollowupSettings(),
        "receptivity": ReceptivityState(scope.owner_id, scope.subject_id),
        "clock": clock,
        "calendar": calendar_snapshot(scope=scope, clock=clock),
        "profile_revision": payload["scope"]["revision"],
        "subscription_state": BriefSourceState(basis.source_id, scope, basis.revision, basis.value_sha256),
        "transit": payload,
        "transit_state": BriefSourceState(
            payload["document_id"], scope, payload["scope"]["revision"], payload["document_id"][5:]
        ),
        "items": (
            item(1, scope, due=AT + timedelta(hours=8), area="career"),
            item(2, scope, due=AT + timedelta(hours=10), area="wellbeing"),
            item(3, scope, due=AT - timedelta(hours=13), area="family"),
        ),
    }


def workload(values: dict) -> int:
    for _ in range(100):
        result = compose_briefing(**values)
        assert result.delivery.disposition == "push"
        sections = {section.id: section for section in result.sections}
        assert "area_career" in sections and "area_wellbeing" in sections and "area_family" not in sections
        assert len(sections["transit"].lines) == 6
        assert all("北京时间12:00快照" in line.text for line in sections["transit"].lines)
        assert all("SYNTHETIC_BRIEF_ITEM_3" not in line.text for section in result.sections for line in section.lines)
        assert any(item.reason == "reminder_older_than_twelve_hours" for item in result.omissions)
        assert result.effects.model_calls == result.effects.writes == result.effects.notifications == 0
    return 100


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().exists():
        raise ValueError("briefing_benchmark_output_must_be_new")
    values = arguments(json.loads(FIXTURE.read_bytes()))
    paths = [*Path("mingjing_core/application/briefing_v2").glob("*.py"), Path(__file__), FIXTURE]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    cases = [measure("full_synthetic_p8_briefing_100", lambda: workload(values))]
    if before != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}:
        raise ValueError("briefing_benchmark_source_changed")
    write_report(args.output, cases, paths, clock=SystemClock())
    print("full_synthetic_p8_briefing_100", cases[0]["median_seconds"], cases[0]["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()
