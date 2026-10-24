"""Prepare all 80 original questions for v4, with the approved two-channel X03."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay, split_recovery_contract


def write_full_corpus(source: Path, destination: Path) -> dict[str, int]:
    originals = load_scenarios(source)
    if len(originals) != 80 or sum(case.id == "X03" for case in originals) != 1:
        raise ValueError("完整评测需要原80题及唯一的X03")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("请提供新的空输出目录，既有语料不会被覆盖")
    cases = [
        variant for case in originals for variant in (split_recovery_contract(case) if case.id == "X03" else [case])
    ]
    serialized = {
        case.id: yaml.safe_dump(
            execution_overlay(case).model_dump(mode="json", exclude_defaults=True, exclude_none=True),
            allow_unicode=True,
            sort_keys=False,
        )
        for case in cases
    }
    if len(serialized) != 81:
        raise ValueError("完整评测的80题应展开为81个渠道用例")
    destination.mkdir(parents=True, exist_ok=True)
    for identity, data in serialized.items():
        with (destination / f"{identity}.yaml").open("x", encoding="utf-8", newline="\n") as output:
            output.write(data)
    return {"questions": 80, "execution_cases": 81, "approved_channel_splits": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "scenarios")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_full_corpus(args.source, args.output)))


if __name__ == "__main__":
    main()
