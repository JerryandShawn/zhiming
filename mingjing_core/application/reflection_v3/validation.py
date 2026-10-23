"""Private pure projections use fixed errors and opaque metadata; host authentication remains external."""

import hashlib
import json
import re
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, TypeVar

from mingjing_core.memory2.contracts import MemoryScope, MemorySnapshot, utc
from mingjing_core.memory2.validation import require_bool, require_int

T = TypeVar("T")


class ReflectionError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("记忆整理资料暂不可用，请核对归属、来源与当前许可")


def opaque(*values: str) -> None:
    if any(
        type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", value) is None for value in values
    ):
        raise ReflectionError("opaque_identifier_required")


def digest(value: Any) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ReflectionError("fingerprint_input_invalid") from None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sha(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ReflectionError("fingerprint_invalid")


def typed_tuple(value: object, cls: type[T]) -> tuple[T, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, cls) for item in value):
        raise ReflectionError("typed_sequence_required")
    return tuple(value)


def identities(value: object, *, minimum: int = 1) -> tuple[str, ...]:
    values = typed_tuple(value, str)
    opaque(*values)
    if len(values) < minimum or len(set(values)) != len(values):
        raise ReflectionError("source_identity_set_invalid")
    return values


def instant(value: datetime) -> datetime:
    try:
        return utc(value)
    except (TypeError, ValueError, OverflowError):
        raise ReflectionError("aware_instant_required") from None


def scope_snapshot(snapshot: MemorySnapshot, scope: MemoryScope) -> None:
    if not isinstance(snapshot, MemorySnapshot) or not isinstance(scope, MemoryScope) or snapshot.scope != scope:
        raise ReflectionError("scope_mismatch")
    identities = [(fact.owner_id, fact.subject_id) for fact in snapshot.facts]
    identities.extend((source.owner_id, source.subject_id) for source in snapshot.sources)
    if any(identity != (scope.owner_id, scope.subject_id) for identity in identities):
        raise ReflectionError("snapshot_scope_mismatch")


def integer(value: int, minimum: int = 0) -> None:
    try:
        require_int(value, minimum)
    except ValueError:
        raise ReflectionError("integer_required") from None


def booleans(*values: bool) -> None:
    try:
        require_bool(*values)
    except ValueError:
        raise ReflectionError("boolean_required") from None


def dataclass_json(value: Any) -> Any:
    """Canonical representation of trusted typed projections, including exact UTC timestamps."""
    if hasattr(value, "__dataclass_fields__"):
        return dataclass_json(asdict(value))
    if isinstance(value, datetime):
        return instant(value).isoformat()
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, dict):
        return {key: dataclass_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [dataclass_json(item) for item in value]
    return value
