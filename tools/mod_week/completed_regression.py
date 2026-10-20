"""Sequential offline module regression; every round must start in Beijing minutes 45–59."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import Clock, SystemClock  # noqa: E402

ZONE = ZoneInfo("Asia/Shanghai")
SUITES = (
    "organize",
    "validation",
    "followups_mod",
    "cards_mod",
    "mod_tools",
    "mod_week",
    "timeparse",
    "memory2",
    "streaming",
    "scheduling",
    "organize_v2",
    "p9_v2",
)


def window_time(clock: Clock) -> datetime:
    instant = clock.now()
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("regression_clock_must_be_aware")
    local = instant.astimezone(ZONE)
    if not 45 <= local.minute < 60:
        raise ValueError("full_regression_outside_beijing_window")
    return local


def environment() -> dict[str, str]:
    values = dict(os.environ)
    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        values.pop(name, None)
    values.update(PYTHONDONTWRITEBYTECODE="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
    values["TEMP"] = values["TMP"] = str(ROOT / "private/mod-week/tmp")
    return values


def run_round(clock: Clock, index: int, stamp: str) -> dict:
    started = window_time(clock)
    temporary = ROOT / "private/mod-week/tmp" / f"completed-{stamp}-{index}"
    if not temporary.resolve().is_relative_to((ROOT / "private/mod-week/tmp").resolve()):
        raise ValueError("regression_temp_outside_workspace")
    command = [
        "-m",
        "pytest",
        *(f"tests/v4/{name}" for name in SUITES),
        "-q",
        f"--basetemp={temporary}",
    ]
    result = subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        env=environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    return {
        "round": index,
        "started_at": started.isoformat(),
        "finished_at": clock.now().astimezone(ZONE).isoformat(),
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.exists() or not output.parent.is_dir():
        raise ValueError("regression_output_must_be_new_file_inside_workspace")
    clock = SystemClock()
    stamp = window_time(clock).strftime("%Y%m%d-%H%M%S")
    rounds = []
    for index in range(1, args.rounds + 1):
        current = run_round(clock, index, stamp)
        rounds.append(current)
        print(current["stdout"].splitlines()[-1] if current["stdout"].splitlines() else "no_test_summary", flush=True)
        if current["exit_code"]:
            break
    report = {"scope": "completed offline module suites Q1-Q6 only; no PG/live model/HTTP", "rounds": rounds}
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if any(item["exit_code"] for item in rounds):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
