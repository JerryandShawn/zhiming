"""1000 synthetic records: scoped partition selection and revoked-summary invalidation."""

import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.memory.retrieval_types import SearchSource, SearchUnit, SourceRef  # noqa: E402
from mingjing_core.organize.partition_context_v2 import (  # noqa: E402
    plan_summary_invalidations,
    project_partition_context,
)
from mingjing_core.organize.partition_context_v2_contracts import PartitionRecord, PartitionScope  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = PartitionScope("synthetic-partition-owner", "self", "life:self", "career", "interview")


def fixtures(count: int = 1000):
    records, sources = [], []
    for index in range(count):
        source = SearchSource(f"synthetic-source-{index}", SCOPE.owner_id, SCOPE.subject_id)
        sources.append(source)
        summary = index % 5 == 0
        unit = SearchUnit(
            f"synthetic-unit-{index}",
            SCOPE.owner_id,
            SCOPE.subject_id,
            "summary" if summary else "fact",
            "合成分区近况。此为性能样例。",
            AT - timedelta(hours=index % 240),
            origin="derived_summary" if summary else "user",
            source_refs=(SourceRef(source.id),),
            category="constraint" if index % 17 == 0 and not summary else "background",
            inferred=summary,
        )
        records.append(
            PartitionRecord(
                unit,
                SCOPE.life_thread_id,
                ("career", "health", "family")[index % 3],
                "summary" if summary else "retrieval",
                None,
                (index % 11) / 10,
            )
        )
    return tuple(records), tuple(sources)


def project_workload(records, sources):
    result = project_partition_context(records, sources, scope=SCOPE, source_epoch=0, clock=FrozenClock(AT))
    assert len(result.constraints) == 47 and len(result.retrieval) == 753
    assert len(result.recent_elsewhere) == 4 and result.current_summary
    assert all(line.space_id != SCOPE.space_id for line in result.recent_elsewhere)
    return len(records)


def invalidate_workload(records, sources):
    withdrawn = tuple(replace(source, redacted=True) for source in sources)
    result = plan_summary_invalidations(records, withdrawn, scope=SCOPE, source_epoch=1, clock=FrozenClock(AT))
    assert len(result.changes) == 200 and all(item.expected_revision == 1 for item in result.changes)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().exists():
        raise ValueError("partition_benchmark_output_must_be_new")
    records, sources = fixtures()
    cases = [
        measure("partition_projection_1000", lambda: project_workload(records, sources)),
        measure("summary_invalidation_scan_1000", lambda: invalidate_workload(records, sources)),
    ]
    paths = [
        Path("mingjing_core/organize/partition_context_v2.py"),
        Path("mingjing_core/organize/partition_context_v2_contracts.py"),
        Path("mingjing_core/memory/retrieval_types.py"),
        Path("mingjing_core/timekit/clock.py"),
        Path(__file__),
    ]
    write_report(args.output, cases, paths, clock=SystemClock())
    for case in cases:
        print(case["name"], "median_seconds", case["median_seconds"], "peak", case["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()
