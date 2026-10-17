"""Explicit P8 entry, retaining v3 isolation, branches, artifacts and pointers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ...domain.json_values import ensure_finite_json
from .adapter import ChartAdapter


class P8ChartAdapter(ChartAdapter):
    """Opt in by importing this class; the default ChartAdapter is unchanged."""

    def _run(self, system: str, args: dict[str, Any]) -> dict[str, Any]:
        if system != "bazi":
            return super()._run(system, args)
        process = subprocess.run(
            [self.python, "-X", "utf8", str(Path(__file__).with_name("p8_worker.py"))],
            input=json.dumps({"system": system, "args": args}, allow_nan=False),
            capture_output=True,
            encoding="utf-8",
            timeout=self.timeout,
        )
        if process.returncode:
            kind = "missing_chart_dependency" if "ModuleNotFoundError" in process.stderr else "chart_engine_failure"
            raise RuntimeError(kind)
        if len(process.stdout) > 8_000_000:
            raise RuntimeError("chart_output_limit_exceeded")
        value = json.loads(process.stdout)
        ensure_finite_json(value)
        return value

    @staticmethod
    def _feature_paths(system: str, data: dict[str, Any]) -> list[tuple[str, str, str]]:
        paths = ChartAdapter._feature_paths(system, data)
        if system == "bazi" and "p8" in data:
            for key in (
                "ten_gods",
                "month_command",
                "strength",
                "patterns",
                "climate",
                "useful_candidates",
                "auxiliary_stars",
            ):
                paths.append(("p8." + key, "/data/p8/" + key, "natal"))
            paths.append(("p8.decade_luck", "/data/p8/decade_luck", "decadal"))
            for key, scale in (
                ("year", "yearly"),
                ("months", "monthly_exact_jie_intervals"),
                ("day", "daily_snapshot"),
            ):
                paths.append(("p8.calendar_layers." + key, "/data/p8/calendar_layers/" + key, scale))
        return paths
