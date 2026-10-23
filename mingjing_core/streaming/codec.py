"""Single-frame SSE codec; framing never grants ownership or source authorization."""

import json
import re
from datetime import datetime, timedelta

from .event_errors import EventValidationError
from .event_models import RunEvent, event_data, make_event

_WIRE_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+08:00")


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EventValidationError("json_duplicate_key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise EventValidationError("json_number_invalid")


def encode_sse(event: RunEvent) -> str:
    if not isinstance(event, RunEvent):
        raise EventValidationError("event_required")
    data = json.dumps(event_data(event), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n"


def _fields(frame: str) -> tuple[str | None, str | None, list[str]]:
    normalized = frame.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n\n") or "\n\n" in normalized[:-2]:
        raise EventValidationError("sse_single_complete_frame_required")
    fields, data = {}, []
    for line in normalized[:-2].split("\n"):
        if line.startswith(":") or not line:
            continue
        name, separator, value = line.partition(":")
        if not separator or name not in {"id", "event", "data"}:
            raise EventValidationError("sse_field_invalid")
        value = value[1:] if value.startswith(" ") else value
        if name == "data":
            data.append(value)
        elif name in fields:
            raise EventValidationError("sse_duplicate_field")
        else:
            fields[name] = value
    return fields.get("id"), fields.get("event"), data


def decode_sse(frame: str | bytes) -> RunEvent | None:
    try:
        if isinstance(frame, bytes):
            frame = frame.decode("utf-8", errors="strict")
        if not isinstance(frame, str):
            raise EventValidationError("sse_text_required")
        identifier, event_type, parts = _fields(frame)
        if identifier is None and event_type is None and not parts:
            return None
        if (
            identifier is None
            or event_type is None
            or not parts
            or not identifier.isascii()
            or not identifier.isdecimal()
        ):
            raise EventValidationError("sse_header_required")
        if identifier != str(int(identifier)):
            raise EventValidationError("sse_id_not_canonical")
        data = json.loads("\n".join(parts), object_pairs_hook=_pairs, parse_constant=_nonfinite)
        return event_from_data(event_type, data, expected_seq=int(identifier))
    except EventValidationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise EventValidationError("sse_invalid") from None


def event_from_data(event_type: str, data: object, *, expected_seq: int | None = None) -> RunEvent:
    if not isinstance(data, dict):
        raise EventValidationError("event_data_object_required")
    common = {"v", "run_id", "seq", "ts"}
    if not common <= data.keys() or type(data["ts"]) is not str:
        raise EventValidationError("event_common_required")
    if _WIRE_TIME.fullmatch(data["ts"]) is None:
        raise EventValidationError("wire_time_format_invalid")
    try:
        timestamp = datetime.fromisoformat(data["ts"])
    except (TypeError, ValueError):
        raise EventValidationError("event_time_invalid") from None
    if timestamp.utcoffset() != timedelta(hours=8):
        raise EventValidationError("wire_timezone_must_be_plus08")
    if type(data["v"]) is not int or data["v"] != 1:
        raise EventValidationError("event_version_invalid")
    if expected_seq is not None and (
        type(expected_seq) is not int or type(data["seq"]) is not int or data["seq"] != expected_seq
    ):
        raise EventValidationError("sse_sequence_mismatch")
    return make_event(
        run_id=data["run_id"],
        seq=data["seq"],
        ts=timestamp,
        type=event_type,
        payload={key: value for key, value in data.items() if key not in common},
    )
