"""Synthetic-only full export conversion/preview/inverse planning observations; never applies data."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.memory2.contracts import MemoryScope, MemorySource  # noqa: E402
from mingjing_core.organize.export_dry_run_v3 import (  # noqa: E402
    DryRunLedger,
    DryRunPlan,
    ExportSnapshot,
    dry_run_export,
    plan_undo_dry_run,
    preview_dry_run,
)
from mingjing_core.streaming.json_values import json_object  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

FIXTURE = ROOT / "tools/eval/fixtures/mod_20261021/v3_export_synthetic.json"


def fixture(count: int) -> tuple[dict[str, Any], ExportSnapshot, FrozenClock]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload, rows, sources = dict(data["export"], messages=[]), {}, []
    scope = MemoryScope(payload["owner_id"], payload["subject_id"])
    base = data["export"]["messages"][1]["at_ms"]
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        key = "career" if role == "user" else "assistant"
        identity = f"synthetic-benchmark-{index}"
        row = {
            "id": identity,
            "owner_id": scope.owner_id,
            "subject_id": scope.subject_id,
            "revision": 1,
            "source_id": "source-" + identity,
            "source_revision": 1,
            "role": role,
            "content": data["texts"][key],
            "at_ms": base + index * 30000,
            "thread_id": "synthetic-thread",
        }
        payload["messages"].append(row)
        rows[identity] = dict(row, status="active", incognito=False, retention_scope="persistent")
        if index % 3:
            rows[identity]["space_secondary"] = None
        sources.append(
            MemorySource(
                row["source_id"],
                scope.owner_id,
                scope.subject_id,
                row["content"],
                datetime.fromtimestamp(row["at_ms"] / 1000, UTC),
                role=role,
            )
        )
    document = {"owner_id": scope.owner_id, "subject_id": scope.subject_id, "messages": rows, "topics": {}}
    snapshot = ExportSnapshot(
        scope, payload["revision"], payload["source_epoch"], document, tuple(sources), synthetic=True
    )
    return payload, snapshot, FrozenClock(datetime.fromisoformat(data["clock_at"]))


def post_state_fixture(plan: DryRunPlan, snapshot: ExportSnapshot) -> ExportSnapshot:
    """Construct only an isolated synthetic expected state for testing inverse preconditions."""
    from dataclasses import replace

    document = json_object(snapshot.document)
    for op in plan.change_set.ops:
        container, key = document[op.collection], op.entity_id
        if op.field is not None:
            container, key = container[key], op.field
        if op.after.present:
            container[key] = op.after.value
        else:
            container.pop(key, None)
    ledger = DryRunLedger(
        plan.operation_id,
        plan.input_fingerprint,
        plan.fingerprint,
        "applied",
        snapshot.revision + 1,
        tuple((item.id, document["messages"][item.id]["revision"]) for item in plan.preconditions),
    )
    return replace(snapshot, revision=snapshot.revision + 1, document=document, operations=(ledger,))


def complete_chain(count: int) -> int:
    from dataclasses import replace

    payload, snapshot, clock = fixture(count)
    original = json_object(snapshot.document)
    plan = dry_run_export(
        payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="synthetic-benchmark"
    )
    assert not plan.conflicts and not plan.waiting_ids and len(plan.preconditions) == count
    preview = preview_dry_run(plan, snapshot=snapshot, scope=snapshot.scope, clock=clock)
    assert preview["counts"]["proposed_labels"] == count and preview["requires_user_review"]
    ledger = DryRunLedger(plan.operation_id, plan.input_fingerprint, plan.fingerprint)
    replay = dry_run_export(
        payload,
        snapshot=replace(snapshot, operations=(ledger,)),
        scope=snapshot.scope,
        clock=clock,
        operation_id=plan.operation_id,
    )
    assert replay.replayed and replay.fingerprint == plan.fingerprint
    post = post_state_fixture(plan, snapshot)
    inverse = plan_undo_dry_run(plan, snapshot=post, scope=post.scope, clock=clock)
    assert inverse.allowed and inverse.inverse_ops == plan.change_set.inverse_ops
    assert json_object(snapshot.document) == original
    return count


def hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("benchmark_output_already_exists")
    sources = tuple(sorted((ROOT / "mingjing_core/organize/export_dry_run_v3").glob("*.py")))
    sources += tuple(sorted((ROOT / "mingjing_core/organize/v2").glob("*.py")))
    sources += (
        ROOT / "mingjing_core/organize/changes.py",
        ROOT / "mingjing_core/organize/_change_values.py",
        ROOT / "mingjing_core/memory2/sensitivity.py",
        FIXTURE,
        Path(__file__).resolve(),
    )
    before = hashes(sources)
    cases = [
        measure(f"synthetic_{count}_messages_export_preview_replay_inverse_plan", lambda n=count: complete_chain(n))
        for count in (120, 500)
    ]
    if hashes(sources) != before:
        raise ValueError("benchmark_source_changed_during_measurement")
    report = write_report(args.output, cases, sources, clock=SystemClock())
    report.update(
        {
            "source_stable_during_measurement": True,
            "source_sha256_before": before,
            "workload_notes": [
                "Each chain includes fixture construction, conversion, authorized preview, "
                "planned-ledger replay and inverse planning.",
                "Alternating user/assistant rows preserve separate full original anchors; "
                "missing/null labels alternate.",
                "The post-state is a synthetic private copy, not a database apply or actual undo.",
                "No real export, classification-quality claim, model, network, database "
                "or business operation is measured.",
            ],
        }
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for case in cases:
        print(case["name"], case["median_seconds"], case["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()
