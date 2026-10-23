"""Full synthetic K3 token consumption paths, including the public-snapshot memory metadata lookup."""

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.action_token_contracts import ActionTokenError  # noqa: E402
from mingjing_core.adapters.channels.action_token_policy_v2 import K3TokenService  # noqa: E402
from mingjing_core.adapters.channels.action_token_refresh_v2 import MemoryTokenMetadataLookup  # noqa: E402
from mingjing_core.adapters.channels.action_token_store import MemoryActionTokenStore  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 21, tzinfo=UTC)
PAYLOAD_FINGERPRINT = hashlib.sha256(b"synthetic-k3-performance-only").hexdigest()


def token_pool(count: int):
    store = MemoryActionTokenStore(capacity=count)
    lookup = MemoryTokenMetadataLookup(store)
    service = K3TokenService(store, clock=FrozenClock(AT), lookup=lookup)
    pairs = []
    for index in range(count):
        claim = dict(
            owner_id="synthetic-benchmark-owner",
            subject_id="self",
            open_id="ou_syntheticBenchmark",
            kind="question",
            entity_id=f"synthetic-entity-{index:05}",
            payload_fingerprint=PAYLOAD_FINGERPRINT,
        )
        pairs.append((service.issue(**claim), claim))
    assert len(store.snapshot()) == count
    return service, store, pairs


def combined_workload(count: int) -> int:
    service, store, pairs = token_pool(count)
    first_effects = replay_effects = 0
    for issued, claim in pairs:
        first = service.consume(issued.token, **claim)
        replay = service.consume(issued.token, **claim)
        first_effects += int(first.should_execute)
        replay_effects += int(replay.should_execute)
        assert first.operation_id == replay.operation_id == issued.operation_id
        assert first.consumption.used_at == replay.consumption.used_at == AT
    assert first_effects == count and replay_effects == 0
    assert sum(record.used_at is not None for record in store.snapshot()) == count
    return count


def tail_replay_workload(count: int):
    service, store, pairs = token_pool(count)
    issued, claim = pairs[-1]
    assert service.consume(issued.token, **claim).should_execute

    def workload() -> int:
        effects = 0
        for _ in range(count):
            result = service.consume(issued.token, **claim)
            effects += int(result.should_execute)
            assert result.operation_id == issued.operation_id and result.consumption.replayed
        assert effects == 0 and sum(record.used_at is not None for record in store.snapshot()) == 1
        return count

    return workload


def tail_wrong_binding_workload(count: int):
    service, store, pairs = token_pool(count)
    issued, claim = pairs[-1]
    wrong = {**claim, "owner_id": "synthetic-other-owner"}

    def workload() -> int:
        invalid = 0
        for _ in range(count):
            try:
                service.consume(issued.token, **wrong)
            except ActionTokenError:
                invalid += 1
            else:
                raise AssertionError("invalid_binding_was_accepted")
        assert invalid == count and all(record.used_at is None for record in store.snapshot())
        return count

    return workload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.count <= 2000 or args.output.exists():
        raise ValueError("benchmark_count_invalid_or_output_already_exists")
    assert combined_workload(min(50, args.count)) == min(50, args.count)
    cases = [
        measure(f"k3_issue_first_consume_replay_{args.count}", lambda: combined_workload(args.count)),
        measure(f"k3_capacity_{args.count}_tail_replay_{args.count}", tail_replay_workload(args.count)),
        measure(f"k3_capacity_{args.count}_tail_wrong_binding_{args.count}", tail_wrong_binding_workload(args.count)),
    ]
    cases[0]["unit"] = "unique token: issue + first consume + replay; all first permissions and zero replay effects"
    cases[0]["fixture_setup_included"] = True
    cases[0]["expected_first_permissions"] = args.count
    cases[0]["expected_replay_effects"] = 0
    cases[0]["additional_small_warmup_tokens"] = min(50, args.count)
    for case in cases[1:]:
        case["unit"] = "one click through the real metadata lookup at the final entry of a full memory store"
        case["fixture_setup_included"] = False
        case["fixed_store_capacity"] = args.count
        case["expected_effects"] = 0
    base = ROOT / "mingjing_core/adapters/channels"
    sources = [
        base / "action_token_policy_v2.py",
        base / "action_token_refresh_v2.py",
        base / "action_token_contracts.py",
        base / "action_token_store.py",
        base / "action_tokens.py",
        Path(__file__),
        ROOT / "tools/mod_week/performance.py",
    ]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(
            result["name"],
            "median_seconds",
            result["median_seconds"],
            "separate_python_peak_bytes",
            result["separate_tracemalloc_peak_bytes"],
        )


if __name__ == "__main__":
    main()
