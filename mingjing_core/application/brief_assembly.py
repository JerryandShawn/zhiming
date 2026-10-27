"""Pure, source-checked brief input assembly. No generation, scheduling, or delivery."""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from mingjing_core.domain.report_schedules import report_period_bounds
from mingjing_core.timekit.clock import Clock, FrozenClock
from mingjing_core.timekit.now_block import render_now_block

from .decision_autonomy_rules import dependency_copy_warnings
from .followups_contracts import FollowupScope, aware


@dataclass(frozen=True)
class BriefMaterial:
    source_id: str
    scope: FollowupScope
    revision: int
    alias: str
    kind: Literal["profile", "agenda", "followup", "transit", "episode"]
    text: str = field(repr=False)
    at: datetime | None = None
    profile_revision: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, FollowupScope)
            or not isinstance(self.source_id, str)
            or not self.source_id
        ):
            raise ValueError("brief material requires scope and source")
        if (
            type(self.revision) is not int
            or self.revision < 1
            or not re.fullmatch(r"[a-z][1-9]\d*", self.alias)
        ):
            raise ValueError("brief material revision or alias invalid")
        if self.kind not in {"profile", "agenda", "followup", "transit", "episode"}:
            raise ValueError("brief material kind invalid")
        if (
            not isinstance(self.text, str)
            or not self.text.strip()
            or len(self.text) > 2000
        ):
            raise ValueError("brief material text invalid")
        if self.at is not None:
            object.__setattr__(self, "at", aware(self.at))
        if self.profile_revision is not None and (
            type(self.profile_revision) is not int or self.profile_revision < 1
        ):
            raise ValueError("brief profile revision invalid")

    @property
    def digest(self) -> str:
        value = [
            self.kind,
            self.text,
            self.at.isoformat() if self.at else None,
            self.profile_revision,
        ]
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False).encode()
        ).hexdigest()


@dataclass(frozen=True)
class BriefSource:
    source_id: str
    scope: FollowupScope
    revision: int
    digest: str
    active: bool = True
    revoked: bool = False
    incognito: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, FollowupScope)
            or not isinstance(self.source_id, str)
            or not self.source_id
        ):
            raise ValueError("brief source scope invalid")
        if (
            type(self.revision) is not int
            or self.revision < 1
            or not re.fullmatch(r"[a-f0-9]{64}", self.digest)
        ):
            raise ValueError("brief source version invalid")
        if any(
            type(value) is not bool
            for value in (self.active, self.revoked, self.incognito)
        ):
            raise ValueError("brief source flags invalid")


@dataclass(frozen=True)
class BriefAssembly:
    scope: FollowupScope
    send_at: datetime
    period_start: date
    period_end: date
    now_block: str = field(repr=False)
    materials: tuple[BriefMaterial, ...] = field(repr=False)
    omissions: tuple[tuple[str, str], ...]
    preview: str = "明镜的晨报到了"


def _accept_material(
    row: BriefMaterial,
    source: BriefSource | None,
    *,
    day: date,
    timezone: str,
    confirmed_profile_revision: int | None,
) -> str | None:
    if source is None or not source.active or source.revoked or source.incognito:
        return "source_unavailable"
    if (source.revision, source.digest) != (row.revision, row.digest):
        return "source_changed"
    if dependency_copy_warnings(row.text):
        return "dependency_copy"
    if row.kind == "transit":
        if (
            confirmed_profile_revision is None
            or row.profile_revision != confirmed_profile_revision
        ):
            return "unconfirmed_profile"
        if row.at is None or row.at.astimezone(ZoneInfo(timezone)).date() != day:
            return "wrong_transit_day"
    if row.kind in {"agenda", "followup"} and (
        row.at is None
        or not day
        <= row.at.astimezone(ZoneInfo(timezone)).date()
        <= day + timedelta(days=7)
    ):
        return "outside_upcoming_window"
    return None


def assemble_brief(
    materials: Sequence[BriefMaterial],
    sources: Sequence[BriefSource],
    *,
    scope: FollowupScope,
    send_at: datetime,
    clock: Clock,
    timezone: str = "Asia/Shanghai",
    report_kind: str = "daily",
    confirmed_profile_revision: int | None = None,
) -> BriefAssembly:
    """Caller supplies current authorized sources; delivery must reload them in its transaction."""
    now, send = aware(clock.now()), aware(send_at)
    zone = ZoneInfo(timezone)
    if not timedelta(0) <= send - now <= timedelta(minutes=15):
        raise ValueError("brief preparation must be within fifteen minutes of sending")
    if confirmed_profile_revision is not None and (
        type(confirmed_profile_revision) is not int or confirmed_profile_revision < 1
    ):
        raise ValueError("confirmed profile revision invalid")
    if any(row.scope != scope for row in (*materials, *sources)):
        raise ValueError("brief source scope mismatch")
    if len({row.source_id for row in sources}) != len(sources) or len(
        {row.alias for row in materials}
    ) != len(materials):
        raise ValueError("brief source or alias collision")
    manifest, accepted, omitted = {row.source_id: row for row in sources}, [], []
    day = send.astimezone(zone).date()
    bounds = report_period_bounds(report_kind, day)
    for row in materials:
        reason = _accept_material(
            row,
            manifest.get(row.source_id),
            day=day,
            timezone=timezone,
            confirmed_profile_revision=confirmed_profile_revision,
        )
        if row.kind == "episode" and (
            row.at is None
            or not date.fromisoformat(bounds["start"])
            <= row.at.astimezone(zone).date()
            <= date.fromisoformat(bounds["end"])
        ):
            reason = "outside_report_period"
        if reason:
            omitted.append((row.alias, reason))
        else:
            accepted.append(row)
    events = [
        {"id": row.alias, "content": row.text, "event_at": row.at}
        for row in accepted
        if row.kind in {"agenda", "followup"}
    ]
    block = render_now_block(
        {"timezone": timezone}, FrozenClock(send), upcoming_events=events
    )
    return BriefAssembly(
        scope,
        send,
        date.fromisoformat(bounds["start"]),
        date.fromisoformat(bounds["end"]),
        block,
        tuple(accepted),
        tuple(omitted),
    )
