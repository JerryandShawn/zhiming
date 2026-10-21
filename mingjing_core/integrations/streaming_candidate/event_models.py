"""Frozen v1 events carry no owner identifier onto the public SSE wire."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

from pydantic import ValidationError

from .event_errors import EventValidationError
from .event_payloads import PAYLOAD_MODELS
from .json_values import freeze_json, json_object, thaw_json

SHANGHAI = timezone(timedelta(hours=8))


def _identifier(value: object) -> None:
    if type(value) is not str or len(value) > 200 or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value) is None:
        raise EventValidationError("identifier_required")


def _payload(event_type: object, payload: object) -> Mapping:
    if type(event_type) is not str or event_type not in PAYLOAD_MODELS:
        raise EventValidationError("event_type_unknown")
    try:
        model = PAYLOAD_MODELS[event_type].model_validate(json_object(payload))
    except (ValidationError, TypeError, ValueError, RecursionError):
        raise EventValidationError("payload_invalid") from None
    data = model.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return freeze_json(data)


@dataclass(frozen=True)
class RunScope:
    owner_id: str
    run_id: str

    def __post_init__(self) -> None:
        _identifier(self.owner_id)
        _identifier(self.run_id)


@dataclass(frozen=True)
class EventDraft:
    type: str
    payload: Mapping = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _payload(self.type, self.payload))


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    seq: int
    ts: datetime
    type: str
    payload: Mapping = field(repr=False)
    v: int = 1

    def __post_init__(self) -> None:
        _identifier(self.run_id)
        if type(self.seq) is not int or self.seq < 1 or type(self.v) is not int or self.v != 1:
            raise EventValidationError("event_counter_invalid")
        if not isinstance(self.ts, datetime) or self.ts.tzinfo is None or self.ts.utcoffset() is None:
            raise EventValidationError("event_time_must_be_aware")
        object.__setattr__(self, "ts", self.ts.astimezone(UTC))
        object.__setattr__(self, "payload", _payload(self.type, self.payload))


def make_event(*, run_id: str, seq: int, ts: datetime, type: str, payload: Mapping) -> RunEvent:
    return RunEvent(run_id, seq, ts, type, payload)


def event_data(event: RunEvent) -> dict:
    if not isinstance(event, RunEvent):
        raise EventValidationError("event_required")
    return {
        "v": event.v,
        "run_id": event.run_id,
        "seq": event.seq,
        "ts": event.ts.astimezone(SHANGHAI).isoformat(),
        **thaw_json(event.payload),
    }
