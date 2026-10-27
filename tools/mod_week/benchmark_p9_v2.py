"""Synthetic K3 lookup-policy, namespace CAS and metadata-codec performance, without transport."""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.action_token_policy_v2 import TTL_BY_KIND, ttl_for_kind  # noqa: E402
from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardScope  # noqa: E402
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import (  # noqa: E402
    ReconciliationBinding,
    merge_cardkit_reconciliation,
    namespace_fingerprint,
)
from mingjing_core.adapters.channels.stream_outbox_v2 import (  # noqa: E402
    StreamIntent,
    StreamScope,
    StreamState,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402


def ttl_workload() -> int:
    for _ in range(1000):
        for kind, duration in TTL_BY_KIND.items():
            assert ttl_for_kind(kind, asserted_action=kind) == duration
    return 1000 * len(TTL_BY_KIND)


def namespace_workload() -> int:
    scope = CardScope("synthetic", "self", "open", "business")
    binding = ReconciliationBinding.for_card(scope, outbox_id="outbox", run_id="run")
    current, row = {"evidence_ref": "retained_synthetic_proof", "other": {"writer": [1]}}, 0
    for index in range(500):
        result = merge_cardkit_reconciliation(
            current,
            binding=binding,
            current_row_revision=row,
            expected_row_revision=row,
            expected_namespace_fingerprint=namespace_fingerprint(current),
            checkpoint=replace(CardCheckpoint(scope), version=index),
        )
        current, row = result.as_dict(), result.next_row_revision
    assert current["evidence_ref"] == "retained_synthetic_proof" and current["other"] == {"writer": [1]}
    return 500


def metadata_workload() -> int:
    scope = StreamScope("synthetic", "self", "outbox", "run", "business", "feishu", "open")
    initial = StreamState(scope, StreamIntent("operation", "create", "a" * 64))
    for _ in range(1000):
        assert restore_state(state_metadata(initial), scope=scope) == initial
    return 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [
        measure(name, fn)
        for name, fn in (
            ("k3_ttl_allowlist_8000", ttl_workload),
            ("namespace_cas_500", namespace_workload),
            ("stream_metadata_roundtrip_1000", metadata_workload),
        )
    ]
    base = Path("mingjing_core/adapters/channels")
    sources = [*base.glob("*_v2.py"), *(base / "stream_outbox_v2").glob("*.py"), Path(__file__)]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(result["name"], "median_seconds", result["median_seconds"])


if __name__ == "__main__":
    main()
