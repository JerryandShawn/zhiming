"""Write a new local readiness report; no product execution or external requests."""

import argparse
import json
from pathlib import Path

from mingjing_core.timekit.clock import SystemClock

from .loader import MaterialError, load_materials
from .report import build_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if not output.is_relative_to(root) or output.exists() or not output.parent.is_dir():
        raise MaterialError("report_requires_new_workspace_path")
    report = build_readiness(load_materials(), clock=SystemClock())
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"case_count": report["case_count"], "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
