"""Measure local official candidate rendering only, including receipts and nested wire budgets."""

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.cards_contracts import BriefSection, ReceiptLine, RouteLabel  # noqa: E402
from mingjing_core.adapters.channels.cards_official_v3 import answer_card, brief_card, card_sizes  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

TOKEN = "synthetic-action-token-000000000000"
TEXT = ('合成引用"\\路径😀' * 2000)[:20_000]


def answers() -> int:
    for _ in range(1000):
        card = answer_card(
            TEXT,
            evidence=TEXT,
            receipts=(ReceiptLine("receipt", "updated", "合成已确认改动", TOKEN + "1"),),
            route=RouteLabel("工作", "合成话题", TOKEN + "2", TOKEN + "3"),
            open_url="https://example.invalid/app",
        )
        inner, wire = card_sizes(card)
        assert inner <= 28_000 and wire <= 30_000
        assert sum(item["tag"] == "button" for item in card["body"]["elements"]) == 4
    return 1000


def briefs() -> int:
    sections = tuple(BriefSection(f"合成区{i}", ('合成引用\\"😀' * 200,) * 30) for i in range(7))
    for _ in range(100):
        card = brief_card(
            date(2026, 10, 21),
            calendar="星期三",
            plans="合成安排",
            daily_flow="仅离线候选",
            closing="按自己的节奏。",
            sections=sections,
            open_url="https://example.invalid/app",
        )
        assert card_sizes(card)[1] <= 30_000
        assert card["body"]["elements"][-1]["tag"] == "button"
    return 100


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT) or destination.exists() or not destination.parent.is_dir():
        raise ValueError("benchmark_output_must_be_new_inside_workspace")
    product = ROOT / "mingjing_core/adapters/channels/cards_official_v3"
    sources = [
        *product.glob("*.py"),
        ROOT / "mingjing_core/adapters/channels/card_limits_official_v3.py",
        ROOT / "mingjing_core/adapters/channels/cards_contracts.py",
        Path(__file__),
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    cases = [
        measure("1000 large answers with real typed receipts and four actions", answers, repeats=3),
        measure("100 large seven-area briefs with nested wire budget", briefs, repeats=3),
    ]
    if before != {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}:
        raise ValueError("benchmark_source_changed")
    report = write_report(destination, cases, sources, clock=SystemClock())
    for case in report["cases"]:
        print(case["name"], case["median_seconds"], case["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()
