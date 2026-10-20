"""Local SSE batching/store/codec observations; no HTTP or PostgreSQL connection."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.streaming.coalescer import DeltaBuffer, feed_delta, flush_delta  # noqa: E402
from mingjing_core.streaming.codec import decode_sse, encode_sse  # noqa: E402
from mingjing_core.streaming.event_models import EventDraft, RunScope  # noqa: E402
from mingjing_core.streaming.memory_event_store import MemoryEventStore  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 17, tzinfo=UTC)


def events_workload(count: int) -> int:
    store = MemoryEventStore(clock=FrozenClock(AT))
    scopes = [RunScope("synthetic", f"run{index}") for index in range(4)]
    draft = EventDraft("text_delta", {"text": "合成🙂\n文本"})
    for index in range(count):
        item = store.append(scopes[index % 4], draft, operation_id=f"op{index}").event
        assert decode_sse(encode_sse(item)) == item
    assert sum(len(store.replay(scope).events) for scope in scopes) == count
    return count


def batching_workload(count: int) -> int:
    clock, state, characters = FrozenClock(AT), DeltaBuffer(RunScope("synthetic", "batch")), 0
    for _ in range(count):
        clock.advance(timedelta(milliseconds=10))
        emission = feed_delta(state, "中文字", generation=0, clock=clock)
        characters += sum(len(draft.payload["text"]) for draft in emission.drafts)
        state = emission.state
    characters += sum(len(draft.payload["text"]) for draft in flush_delta(state, clock=clock).drafts)
    assert characters == count * 3
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [
        measure("sse_append_codec_replay_1000", lambda: events_workload(1000)),
        measure("sse_batch_5000_chunks", lambda: batching_workload(5000)),
    ]
    sources = [*Path("mingjing_core/streaming").glob("*.py"), Path(__file__)]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(result["name"], "median_seconds", result["median_seconds"])


if __name__ == "__main__":
    main()
