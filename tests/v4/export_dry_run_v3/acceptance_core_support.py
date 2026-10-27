"""Independent host doubles. Applying operations here only simulates candidate field transformations."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mingjing_core.memory2.contracts import MemoryScope, MemorySource
from mingjing_core.organize.export_dry_run_v3 import SCHEMA, DryRunLedger, ExportSnapshot
from mingjing_core.streaming.json_values import thaw_json
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
TEXTS = json.loads((ROOT / "tools/eval/fixtures/mod_20261021/v3_export_acceptance_core_synthetic.json").read_bytes())[
    "texts"
]
SCOPE = MemoryScope("synthetic-independent-owner", "synthetic-independent-self")
AT = datetime(2026, 10, 21, tzinfo=UTC)
CLOCK = FrozenClock(AT)
INVALID_UNDO_STATES = (
    "missing",
    "planned",
    "wrong_plan",
    "wrong_input",
    "wrong_global",
    "wrong_target",
    "missing_target",
    "extra_target",
    "same_global",
    "older_global",
)


def message(index=1, *, text_key="career", role="user", seconds=0, thread="synthetic-thread"):
    instant = AT - timedelta(days=1) + timedelta(seconds=seconds)
    return {
        "id": f"synthetic-message-{index}",
        "owner_id": SCOPE.owner_id,
        "subject_id": SCOPE.subject_id,
        "revision": 1,
        "source_id": f"synthetic-source-{index}",
        "source_revision": 1,
        "role": role,
        "content": TEXTS[text_key],
        "at_ms": int(instant.timestamp() * 1000),
        "thread_id": thread,
    }


def fixture(*rows, labels=None):
    rows = list(rows) if rows else [message()]
    payload = {
        "schema": SCHEMA,
        "synthetic": True,
        "export_id": "synthetic-independent-export",
        "owner_id": SCOPE.owner_id,
        "subject_id": SCOPE.subject_id,
        "revision": 4,
        "source_epoch": 6,
        "messages": deepcopy(rows),
    }
    document = {"owner_id": SCOPE.owner_id, "subject_id": SCOPE.subject_id, "messages": {}, "topics": {}}
    sources = []
    for row in rows:
        document["messages"][row["id"]] = {
            **row,
            "status": "active",
            "incognito": False,
            "retention_scope": "persistent",
            **(labels or {}),
        }
        sources.append(
            MemorySource(
                row["source_id"],
                row["owner_id"],
                row["subject_id"],
                row["content"],
                datetime.fromtimestamp(row["at_ms"] / 1000, UTC),
                role=row["role"],
                origin="current_user" if row["role"] == "user" else "assistant",
            )
        )
    return payload, ExportSnapshot(SCOPE, 4, 6, document, tuple(sources), synthetic=True)


def changed_document(snapshot, transform):
    document = thaw_json(snapshot.document)
    transform(document)
    return replace(snapshot, document=document)


def apply_fields(document, operations):
    result = deepcopy(document)
    for operation in operations:
        collection = result[operation.collection]
        if operation.field is None:
            if operation.after.present:
                collection[operation.entity_id] = operation.after.value
            else:
                collection.pop(operation.entity_id, None)
        elif operation.after.present:
            collection[operation.entity_id][operation.field] = operation.after.value
        else:
            collection[operation.entity_id].pop(operation.field, None)
    return result


def applied(snapshot, plan):
    document = apply_fields(thaw_json(snapshot.document), plan.change_set.ops)
    revisions = tuple((item.id, document["messages"][item.id]["revision"]) for item in plan.preconditions)
    ledger = DryRunLedger(plan.operation_id, plan.input_fingerprint, plan.fingerprint, "applied", 5, revisions)
    return replace(snapshot, document=document, revision=5, operations=(ledger,))
