"""Sequential offline module regression; every round must start in Beijing minutes 45–59."""

import argparse
import hashlib
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
    "timeparse_extended",
    "cross_modules",
    "briefing_v2",
    "organize_supplement",
    "organize_supplement_v2",
    "partition_context_v2",
    "day_pipeline",
    "p9_official_v3",
    "eval_material_v23",
    "calibration_v3",
    "export_dry_run_v3",
    "reports_v2",
    "reflection_v3",
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
    values.update(
        PYTHONDONTWRITEBYTECODE="1",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    values["TEMP"] = values["TMP"] = str(ROOT / "private/mod-week/tmp")
    return values


def source_snapshot() -> dict[str, str]:
    """Hash only source/tests, never reopen B or collect private/model-data files."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "mingjing_core"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split("\0")
    paths = {ROOT / value for value in tracked if value.endswith(".py")}
    paths.update((ROOT / "mingjing_core/timeparse").glob("*.py"))
    for suite in SUITES:
        paths.update((ROOT / "tests/v4" / suite).rglob("*.py"))
    paths.update(material_paths())
    paths.add(Path(__file__).resolve())
    if "cross_modules" in SUITES:
        paths.add(ROOT / "mingjing_core/memory2/event_time_extended_v2.py")
    if "eval_material_v23" in SUITES:
        paths.update((ROOT / "tools/eval_material_v23").glob("*.py"))
        for name in ("manifest.json", "casebook.schema.json", "observation.schema.json", "scenarios.v23.yaml"):
            paths.add(ROOT / "tools/eval_material_v23" / name)
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
        if path.is_file() and "__pycache__" not in path.parts
    }


def material_paths() -> set[Path]:
    """Only explicit new synthetic/golden inputs; no blind-B or private calibration material."""
    paths: set[Path] = set()
    if "calibration_v3" in SUITES:
        paths.update((ROOT / "tools/calibration_v3").glob("*.py"))
        paths.update((ROOT / "tools/calibration_v3").glob("*.json"))
    if "export_dry_run_v3" in SUITES:
        paths.update(
            ROOT / name
            for name in (
                "tools/eval/fixtures/mod_20261021/v3_export_synthetic.json",
                "tools/eval/fixtures/mod_20261021/v3_export_acceptance_core_synthetic.json",
                "tests/v4/export_dry_run_v3/fixtures/acceptance_core_matrix.json",
            )
        )
    if "reports_v2" in SUITES:
        paths.update(
            ROOT / name
            for name in (
                "tools/eval/fixtures/mod_20261021/reports_calendar_mod_synthetic.json",
                "tests/v4/reports_v2/fixtures/expected_calendar_mod.json",
                "tests/v4/reports_v2/fixtures/expected_calendar_mod.manifest.json",
            )
        )
    if "p9_official_v3" in SUITES:
        paths.update((ROOT / "tests/v4/p9_official_v3/fixtures").glob("*.json"))
    if "reflection_v3" in SUITES:
        paths.update(
            ROOT / name
            for name in (
                "tools/eval/fixtures/mod_20261021/reflection_background_synthetic.json",
                "tools/eval/fixtures/mod_20261021/reflection_calendar_mod_synthetic.json",
                "tests/v4/reflection_v3/fixtures/expected_calendar_mod.json",
                "tests/v4/reflection_v3/fixtures/expected_calendar_mod.manifest.json",
            )
        )
    return paths


def run_round(clock: Clock, index: int, stamp: str) -> dict:
    sources = source_snapshot()
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
    current_sources = source_snapshot()
    drift = sorted(
        path for path in sources.keys() | current_sources.keys() if sources.get(path) != current_sources.get(path)
    )
    return {
        "round": index,
        "started_at": started.isoformat(),
        "finished_at": clock.now().astimezone(ZONE).isoformat(),
        "command": command,
        "exit_code": result.returncode or (2 if drift else 0),
        "pytest_exit_code": result.returncode,
        "source_files": sources,
        "source_drift": drift,
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
    report = {
        "scope": "completed offline module suites explicitly listed; no PG/live model/HTTP",
        "suites": SUITES,
        "rounds": rounds,
    }
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if any(item["exit_code"] for item in rounds):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
