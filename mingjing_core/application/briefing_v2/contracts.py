"""Private immutable briefing projections; they neither authenticate a host nor send messages."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from mingjing_core.application.followups_contracts import FollowupScope, aware
from mingjing_core.scheduling.delivery_contracts import DeliveryPlan, DeliveryRequest
from mingjing_core.streaming.json_values import freeze_json, json_object
from mingjing_core.timekit.calendar_cn import DayStatus


class BriefingError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("晨报资料暂不可用，请核对归属、日期与来源")


def text(value: object, *, maximum: int = 300) -> None:
    if type(value) is not str or not value.strip() or len(value) > maximum or any(ord(char) < 32 for char in value):
        raise BriefingError("invalid_text_identity")


def integer(value: object, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise BriefingError("invalid_integer")


def sha(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise BriefingError("invalid_fingerprint")


@dataclass(frozen=True)
class BasisRef:
    alias: str
    source_id: str
    revision: int
    owner_id: str
    subject_id: str
    value_sha256: str
    document_id: str | None = None
    path: str | None = None
    claim_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.alias, self.source_id, self.owner_id, self.subject_id):
            text(value)
        if re.fullmatch(r"[a-z][1-9][0-9]*", self.alias) is None:
            raise BriefingError("invalid_local_alias")
        integer(self.revision)
        sha(self.value_sha256)
        if self.document_id is not None:
            text(self.document_id)
        if self.path is not None and (type(self.path) is not str or not self.path.startswith("/")):
            raise BriefingError("invalid_evidence_pointer")
        if self.claim_id is not None and (
            type(self.claim_id) is not str or re.fullmatch(r"claim-[a-f0-9]{64}", self.claim_id) is None
        ):
            raise BriefingError("invalid_evidence_claim_id")


@dataclass(frozen=True)
class BriefSourceState:
    source_id: str
    scope: FollowupScope
    revision: int
    value_sha256: str
    active: bool = True
    revoked: bool = False
    incognito: bool = False

    def __post_init__(self) -> None:
        text(self.source_id)
        integer(self.revision)
        sha(self.value_sha256)
        if not isinstance(self.scope, FollowupScope):
            raise BriefingError("source_scope_required")
        if any(type(value) is not bool for value in (self.active, self.revoked, self.incognito)):
            raise BriefingError("source_flags_invalid")


@dataclass(frozen=True)
class BriefItem:
    request: DeliveryRequest = field(repr=False)
    basis: tuple[BasisRef, ...]
    area_id: str | None = None
    source_states: tuple[BriefSourceState, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.request, DeliveryRequest):
            raise BriefingError("delivery_request_required")
        object.__setattr__(self, "basis", refs(self.basis))
        from mingjing_core.organize.spaces import DEFAULT_SPACES

        if self.area_id is not None and self.area_id not in {space.id for space in DEFAULT_SPACES}:
            raise BriefingError("invalid_brief_area")
        if not isinstance(self.source_states, (tuple, list)) or any(
            not isinstance(item, BriefSourceState) for item in self.source_states
        ):
            raise BriefingError("invalid_current_source_states")
        object.__setattr__(self, "source_states", tuple(self.source_states))
        if len({item.source_id for item in self.source_states}) != len(self.source_states):
            raise BriefingError("duplicate_current_source_states")


def refs(value: object) -> tuple[BasisRef, ...]:
    if not isinstance(value, (list, tuple)) or not value or any(not isinstance(item, BasisRef) for item in value):
        raise BriefingError("bound_basis_required")
    if len({(item.document_id, item.alias) for item in value}) != len(value):
        raise BriefingError("duplicate_basis_alias")
    return tuple(value)


@dataclass(frozen=True)
class CalendarSnapshot:
    scope: FollowupScope
    day: date
    timezone: str
    observed_at: datetime
    almanac: Mapping[str, Any] = field(repr=False)
    day_status: DayStatus
    revision: int = 1

    def __post_init__(self) -> None:
        from .calendar import validate_calendar

        integer(self.revision, 1)
        try:
            object.__setattr__(self, "observed_at", aware(self.observed_at))
            object.__setattr__(self, "almanac", freeze_json(json_object(self.almanac)))
            validate_calendar(self)
        except (TypeError, ValueError, KeyError, OverflowError):
            raise BriefingError("invalid_calendar_snapshot") from None


@dataclass(frozen=True)
class BriefLine:
    text: str = field(repr=False)
    basis: tuple[BasisRef, ...]

    def __post_init__(self) -> None:
        if type(self.text) is not str or not self.text.strip() or len(self.text) > 4000:
            raise BriefingError("invalid_brief_line")
        object.__setattr__(self, "basis", refs(self.basis))


@dataclass(frozen=True)
class BriefSection:
    id: str
    title: str
    lines: tuple[BriefLine, ...] = field(repr=False)

    def __post_init__(self) -> None:
        text(self.id)
        text(self.title, maximum=80)
        if (
            not isinstance(self.lines, (tuple, list))
            or not self.lines
            or any(not isinstance(item, BriefLine) for item in self.lines)
        ):
            raise BriefingError("invalid_brief_section")
        object.__setattr__(self, "lines", tuple(self.lines))


@dataclass(frozen=True)
class BriefOmission:
    item_id: str
    reason: str


@dataclass(frozen=True)
class BriefEffects:
    model_calls: int = 0
    writes: int = 0
    notifications: int = 0
    scheduler_mutations: int = 0

    def __post_init__(self) -> None:
        if any(type(getattr(self, name)) is not int or getattr(self, name) != 0 for name in self.__dataclass_fields__):
            raise BriefingError("effects_must_be_zero")


@dataclass(frozen=True)
class BriefingResult:
    scope: FollowupScope
    day: date
    timezone: str
    generated_at: datetime
    sections: tuple[BriefSection, ...] = field(repr=False)
    basis: tuple[BasisRef, ...]
    delivery: DeliveryPlan | None
    omissions: tuple[BriefOmission, ...]
    warnings: tuple[str, ...]
    request_key: str
    preview: str = field(repr=False)
    effects: BriefEffects = BriefEffects()
