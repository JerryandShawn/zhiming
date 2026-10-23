"""All invented conversation text is loaded from the explicitly marked synthetic fixture."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mingjing_core.memory2.contracts import MemoryScope, MemorySource
from mingjing_core.organize.export_dry_run_v3 import DryRunLedger, DryRunPlan, ExportSnapshot
from mingjing_core.streaming.json_values import json_object
from mingjing_core.timekit.clock import FrozenClock

FIXTURE = json.loads(Path("tools/eval/fixtures/mod_20261021/v3_export_synthetic.json").read_text(encoding="utf-8"))


def material() -> tuple[dict[str, Any], ExportSnapshot, FrozenClock]:
    payload = deepcopy(FIXTURE["export"])
    scope = MemoryScope(payload["owner_id"], payload["subject_id"])
    rows = {}
    sources = []
    for item in payload["messages"]:
        row = dict(item, status="active", incognito=False, retention_scope="persistent")
        row.update(FIXTURE["current_labels"].get(item["id"], {}))
        rows[item["id"]] = row
        sources.append(
            MemorySource(
                item["source_id"],
                scope.owner_id,
                scope.subject_id,
                item["content"],
                datetime.fromtimestamp(item["at_ms"] / 1000, UTC),
                role=item["role"],
            )
        )
    document = {"owner_id": scope.owner_id, "subject_id": scope.subject_id, "messages": rows, "topics": {}}
    snapshot = ExportSnapshot(
        scope, payload["revision"], payload["source_epoch"], document, tuple(sources), synthetic=True
    )
    return payload, snapshot, FrozenClock(datetime.fromisoformat(FIXTURE["clock_at"]))


def retext(payload: dict[str, Any], snapshot: ExportSnapshot, identity: str, key: str) -> ExportSnapshot:
    text = FIXTURE["texts"][key]
    row = next(item for item in payload["messages"] if item["id"] == identity)
    row["content"] = text
    document = json_object(snapshot.document)
    document["messages"][identity]["content"] = text
    sources = tuple(replace(item, text=text) if item.id == row["source_id"] else item for item in snapshot.sources)
    return replace(snapshot, document=document, sources=sources)


def synthetic_post_state(plan: DryRunPlan, snapshot: ExportSnapshot) -> ExportSnapshot:
    """Construct a test-only expected post-state; no production apply/store entry is called."""
    document = json_object(snapshot.document)
    for op in plan.change_set.ops:
        target = document[op.collection]
        key = op.entity_id
        if op.field is not None:
            target, key = target[key], op.field
        if op.after.present:
            target[key] = op.after.value
        else:
            target.pop(key, None)
    ledger = DryRunLedger(
        plan.operation_id,
        plan.input_fingerprint,
        plan.fingerprint,
        "applied",
        snapshot.revision + 1,
        tuple((item.id, document["messages"][item.id]["revision"]) for item in plan.preconditions),
    )
    return replace(snapshot, revision=snapshot.revision + 1, document=document, operations=(ledger,))
