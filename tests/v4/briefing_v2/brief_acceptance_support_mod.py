"""Synthetic trusted-host projections for independent briefing tests, without a DB or sender."""

import json
from datetime import datetime, time
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from mingjing_core.application.briefing_v2 import (
    BasisRef,
    BriefItem,
    BriefSourceState,
    calendar_snapshot,
    compose_briefing,
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

SCOPE = FollowupScope("synthetic-owner-ayuan", "synthetic-subject-ayuan")
BASE = datetime(2026, 10, 21, 7, tzinfo=ZoneInfo("Asia/Shanghai"))
FIXTURES = Path(__file__).parent / "fixtures"
MATRIX = json.loads((FIXTURES / "acceptance_expected_mod.json").read_bytes())


def source_state(ref, **changes):
    values = dict(
        source_id=ref.source_id,
        scope=FollowupScope(ref.owner_id, ref.subject_id),
        revision=ref.revision,
        value_sha256=ref.value_sha256,
    )
    values.update(changes)
    return BriefSourceState(**values)


def context(*, at=BASE, zone="Asia/Shanghai", include_transit=False, scope=SCOPE):
    clock = FrozenClock(at)
    subscription = BriefSubscription(scope, local_time=time(7), time_zone=zone)
    ref = subscription_basis(subscription)
    values = dict(
        scope=scope,
        subscription=subscription,
        settings=FollowupSettings(timezone=zone),
        receptivity=ReceptivityState(scope.owner_id, scope.subject_id),
        clock=clock,
        calendar=calendar_snapshot(scope=scope, clock=clock, timezone=zone),
        profile_revision=1,
        subscription_state=source_state(ref),
        items=(),
    )
    if include_transit:
        transit = json.loads((FIXTURES / "daily_transit_synthetic_20261021.json").read_bytes())
        values.update(
            transit=transit,
            transit_state=BriefSourceState(transit["document_id"], scope, 1, transit["document_id"].split("-", 1)[1]),
        )
    return values


def item(*, due=BASE, index=1, body=None, area="career", kind="reminder", category="ordinary", **changes):
    body = body or f"SYNTHETIC_EVENT_{index}"
    values = dict(
        id=f"notice-{index}",
        owner_id=SCOPE.owner_id,
        subject_id=SCOPE.subject_id,
        kind=kind,
        due_at=due,
        text=body,
        category=category,
        explicit_requested=kind == "reminder",
    )
    values.update(changes)
    candidate = FollowupCandidate(**values)
    ref = BasisRef(
        f"m{index}",
        f"synthetic-source-{index}",
        1,
        candidate.owner_id,
        candidate.subject_id,
        sha256(body.encode("utf-8")).hexdigest(),
    )
    request = DeliveryRequest(f"occurrence-{index}", candidate, candidate.due_at)
    return BriefItem(request, (ref,), area_id=area, source_states=(source_state(ref),))


def public_text(result):
    return "\n".join(
        [
            result.preview,
            *(section.title for section in result.sections),
            *(line.text for section in result.sections for line in section.lines),
        ]
    )


def compose(values, **changes):
    return compose_briefing(**dict(values, **changes))
