"""Synthetic retrieval workload, using explicit time and authorized source snapshots."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.memory.retrieval import SearchSource, SearchUnit, SourceRef, search  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 17, tzinfo=UTC)


def fixtures(count: int) -> tuple[tuple[SearchUnit, ...], tuple[SearchSource, ...]]:
    sources = tuple(SearchSource(f"s{index}", "synthetic", "self") for index in range(count))
    units = tuple(
        SearchUnit(
            f"f{index}",
            "synthetic",
            "self",
            "fact",
            f"第{index}次面试需要准备简历和项目清单",
            AT,
            source_refs=(SourceRef(source.id),),
        )
        for index, source in enumerate(sources)
    )
    return units, sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 100 <= args.count <= 5000:
        raise SystemExit("合成条目数量无效")
    units, sources = fixtures(args.count)

    def workload() -> int:
        for _ in range(10):
            hits = search("synthetic", "self", ["面试"], ["fact"], 20, units=units, source_state=sources, at=AT)
            assert len(hits) == 20
        return args.count * 10

    cases = [measure("memory2_authorized_fts_10_queries", workload)]
    sources_used = [*Path("mingjing_core/memory").glob("retrieval*.py"), Path(__file__)]
    write_report(args.output, cases, sources_used, clock=SystemClock())
    print("memory2 authorized FTS", args.count, "units; median_seconds", cases[0]["median_seconds"])


if __name__ == "__main__":
    main()
