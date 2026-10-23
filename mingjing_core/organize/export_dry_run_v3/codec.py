"""Deliberately explicit synthetic intermediate format, not an unverified production exporter."""

from collections.abc import Mapping
from typing import Any

from mingjing_core.memory2.contracts import MemoryScope, SourceAnchor
from mingjing_core.memory2.validation import require_int, require_text
from mingjing_core.organize._change_values import LABEL_FIELDS, digest
from mingjing_core.streaming.json_values import freeze_json, json_object
from mingjing_core.timekit.clock import Clock

from .contracts import DryRunConflict, DryRunError, ExportMessage, ExportSnapshot, ParsedExport, identifier
from .guards import require_snapshot, row_reason, source_reason

SCHEMA = "zhiming.v3.synthetic_export.v1"
ROOT_FIELDS = frozenset(
    {"schema", "synthetic", "export_id", "owner_id", "subject_id", "revision", "source_epoch", "messages"}
)
ROW_FIELDS = frozenset(
    {
        "id",
        "owner_id",
        "subject_id",
        "revision",
        "source_id",
        "source_revision",
        "role",
        "content",
        "at_ms",
        "thread_id",
    }
)


def parse_export(
    payload: Mapping[str, Any], *, snapshot: ExportSnapshot, scope: MemoryScope, clock: Clock
) -> ParsedExport:
    document = require_snapshot(snapshot, scope)
    try:
        raw = json_object(payload)
        _envelope(raw, snapshot, scope)
        rows = raw["messages"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
            raise DryRunError("message_count_invalid")
        ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
        if any(type(value) is not str or not value for value in ids) or len(set(ids)) != len(ids):
            raise DryRunError("message_ids_invalid")
        source_ids = [row.get("source_id") for row in rows]
        if any(type(value) is not str or not value for value in source_ids) or len(set(source_ids)) != len(source_ids):
            raise DryRunError("message_source_ids_invalid")
        messages, conflicts = [], []
        for row in rows:
            parsed, reason = _message(row, document, snapshot, scope, clock)
            if reason:
                conflicts.append(DryRunConflict(row["id"], reason))
            else:
                messages.append(parsed)
        return ParsedExport(raw["export_id"], digest(raw), freeze_json(raw), tuple(messages), tuple(conflicts))
    except DryRunError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        raise DryRunError("export_invalid") from None


def _envelope(raw: dict[str, Any], snapshot: ExportSnapshot, scope: MemoryScope) -> None:
    if set(raw) != ROOT_FIELDS or raw["schema"] != SCHEMA or raw["synthetic"] is not True:
        raise DryRunError("synthetic_schema_required")
    identifier(raw["export_id"])
    require_int(raw["revision"])
    require_int(raw["source_epoch"])
    if (raw["owner_id"], raw["subject_id"]) != (scope.owner_id, scope.subject_id):
        raise DryRunError("export_scope_mismatch")
    if (raw["revision"], raw["source_epoch"]) != (snapshot.revision, snapshot.source_epoch):
        raise DryRunError("export_snapshot_changed")


def _message(
    row: dict[str, Any], document: dict[str, Any], snapshot: ExportSnapshot, scope: MemoryScope, clock: Clock
) -> tuple[ExportMessage | None, str | None]:
    if set(row) != ROW_FIELDS:
        raise DryRunError("export_row_fields_invalid")
    for name in ("id", "source_id", "thread_id"):
        identifier(row[name])
    if (row["owner_id"], row["subject_id"]) != (scope.owner_id, scope.subject_id):
        raise DryRunError("export_row_scope_mismatch")
    for name in ("revision", "source_revision"):
        require_int(row[name], 1)
    require_int(row["at_ms"])
    require_text(row["source_id"], row["content"], row["thread_id"])
    current = document["messages"].get(row["id"])
    if current is None:
        return None, "row_missing"
    if any(current.get(key) != value or type(current.get(key)) is not type(value) for key, value in row.items()):
        return None, "row_changed"
    reason = row_reason(current)
    source = next((item for item in snapshot.sources if item.id == row["source_id"]), None)
    if reason or source is None:
        return None, reason or "source_missing"
    reason = source_reason(source, now=clock.now())
    if reason:
        return None, reason
    if (source.revision, source.text, source.role, int(source.at.timestamp() * 1000)) != (
        row["source_revision"],
        row["content"],
        row["role"],
        row["at_ms"],
    ):
        return None, "source_original_mismatch"
    anchor = SourceAnchor(source.id, source.revision, 0, len(source.text), source.text)
    label_values = {key: value for key, value in current.items() if key in LABEL_FIELDS}
    parsed = ExportMessage(
        row["id"],
        scope,
        row["revision"],
        source.role,
        source.text,
        row["at_ms"],
        row["thread_id"],
        anchor,
        label_values,
    )
    return parsed, None
