"""Version-aware historical reads do not grant runtime or delivery authorization."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import ValidationError

from .event_errors import EventValidationError
from .event_payloads import Core4Envelope
from .json_values import freeze_json, json_object


@dataclass(frozen=True)
class EnvelopeRead:
    schema: str
    text: str = field(repr=False)
    payload: Mapping = field(repr=False)
    message_id: str | None = None


def read_envelope(value: object) -> EnvelopeRead:
    raw = json_object(value)
    marker = raw.get("schema", raw.get("schema_version"))
    if marker == "core4.0":
        try:
            envelope = Core4Envelope.model_validate(raw)
        except (ValidationError, ValueError, TypeError):
            raise EventValidationError("core4_envelope_invalid") from None
        payload = envelope.model_dump(mode="json", by_alias=True, exclude_unset=True)
        return EnvelopeRead("core4.0", envelope.text, freeze_json(payload), envelope.message_id)
    if marker == "core3.0":
        return _read_core3(raw)
    raise EventValidationError("envelope_version_unknown")


def _read_core3(raw: dict) -> EnvelopeRead:
    # v3's established persisted shape uses schema_version + answer; accepting it
    # for a historical view does not bypass validated_payload/lease/dependency checks.
    if raw.get("schema_version") != "core3.0" or raw.get("schema", "core3.0") != "core3.0":
        raise EventValidationError("core3_envelope_invalid")
    text = raw.get("answer")
    if type(text) is not str or not text.strip():
        raise EventValidationError("core3_answer_required")
    validation = raw.get("validation")
    if not isinstance(validation, dict) or validation.get("valid") is not True or validation.get("schema") != "core3.0":
        raise EventValidationError("core3_validation_required")
    message_id = raw.get("message_id")
    if message_id is not None and type(message_id) is not str:
        raise EventValidationError("core3_message_id_invalid")
    return EnvelopeRead("core3.0", text, freeze_json(raw), message_id)
