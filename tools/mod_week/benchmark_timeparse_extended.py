"""Synthetic mixed-language and scoped-profile normalization, never real profile access."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from mingjing_core.timeparse.extended_v2 import absolutize_extended  # noqa: E402
from mingjing_core.timeparse.profile_contracts_v2 import (  # noqa: E402
    InMemoryProfileDates,
    ProfileDateRecord,
    ProfileScope,
)
from tools.mod_week.performance import measure, write_report  # noqa: E402

REF = datetime(2026, 10, 17, 2, tzinfo=UTC)
SCOPE = ProfileScope("synthetic", "self")
PROFILES = InMemoryProfileDates(
    (
        ProfileDateRecord(
            SCOPE,
            "birthday",
            10,
            28,
            "synthetic-profile-source",
            confirmed=True,
        ),
    )
)
TEXTS = (
    "tomorrow interview",
    "明天下午三点面试",
    "2026-12-31 at 3pm UTC",
    "next Friday review",
    "我生日",
    "04/05/2026 meeting",
    "我妈妈的生日",
    "ordinary notes",
)


def workload() -> int:
    replaced = 0
    for index in range(1000):
        text = TEXTS[index % len(TEXTS)]
        result = absolutize_extended(text, REF, profile_scope=SCOPE, profiles=PROFILES)
        assert result.original_text == text
        if result.result.needs_clarification or result.result.start is None:
            assert not result.replaced and result.text == text
        replaced += result.replaced
    assert replaced == 500
    return 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [measure("mixed_profile_absolutize_1000", workload)]
    sources = [*Path("mingjing_core/timeparse").glob("*.py"), Path(__file__)]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(result["name"], "median_seconds", result["median_seconds"])


if __name__ == "__main__":
    main()
