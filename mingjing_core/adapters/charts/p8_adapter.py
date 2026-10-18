"""Explicit P8 entry, retaining v3 isolation, branches, artifacts and pointers."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from ...calculations.bazi.elements import HIDDEN
from ...domain.json_values import ensure_finite_json
from .adapter import ChartAdapter, validated_number
from .jie_uncertainty import expand
from .named_bazi import options


class P8ChartAdapter(ChartAdapter):
    """Opt in by importing this class; the default ChartAdapter is unchanged."""

    @staticmethod
    def capabilities() -> dict[str, Any]:
        from .p8_policy import release_policy

        return release_policy()

    def __init__(
        self,
        owner_user_id: str,
        python: str | None = None,
        runner: Any = None,
        *,
        timeout: float = 45,
        p8_options: dict[str, str] | None = None,
        transit_period: dict[str, Any] | None = None,
    ) -> None:
        self.p8_options = options(p8_options)
        if transit_period is not None and (
            not isinstance(transit_period, dict)
            or not {"start_at", "end_at"} <= transit_period.keys()
            or set(transit_period) - {"start_at", "end_at", "moving_bodies", "orb", "step_hours"}
        ):
            raise ValueError("行运区间需要显式起止时间与登记的搜索参数")
        self.transit_period = deepcopy(transit_period)
        super().__init__(owner_user_id, python, runner, timeout=timeout)

    def _run(self, system: str, args: dict[str, Any]) -> dict[str, Any]:
        if system != "bazi":
            result = super()._run(system, args)
            if system == "ziwei":
                from .interactions_ziwei import yearly_mutagen_links
                from .p8_worker import source_hashes
                from .ziwei_flying import palace_flying_transformations

                result["data"]["p8_time_interactions"] = yearly_mutagen_links(result["data"])
                result["data"]["p8_flying_transformations"] = palace_flying_transformations(result["data"])
                result["metadata"]["actual_method"]["p8_yearly_links"] = "p8-yearly-mutagen-links-v1"
                result["metadata"]["actual_method"]["p8_flying_transformations"] = result["data"][
                    "p8_flying_transformations"
                ]["version"]
                result["metadata"]["versions"]["p8"] = {"version": "p8-u2-v1", "source_sha256": source_hashes()}
            if system == "astro" and self.transit_period is not None:
                from .p8_worker import source_hashes

                params = dict(
                    self.transit_period,
                    natal_longitudes={key: value["longitude"] for key, value in result["data"]["planets"].items()},
                )
                result["data"]["p8_transit_windows"] = self._request("transit_windows", params)
                result["metadata"]["actual_method"]["p8_transit_interval"] = self.transit_period
                result["metadata"]["versions"]["p8"] = {"version": "p8-u2-v1", "source_sha256": source_hashes()}
            return result
        return self._request(system, dict(args, p8_options=self.p8_options))

    def time_basis(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict) or request.get("owner_user_id") != self.owner_user_id:
            raise ValueError("时间口径核对请求归属不匹配")
        value = dict(request, p8_options=self.p8_options)
        return self._request("time_basis", value)

    def western_timing(self, request: dict[str, Any]) -> dict[str, Any]:
        from .western_timing import validate_timing_request

        validate_timing_request(request, self.owner_user_id)
        return self._request("western_timing", request)

    def _request(self, system: str, args: dict[str, Any]) -> Any:
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

    def _branches(self, birth: dict[str, Any], subject_id: str, revision: int) -> list[dict[str, Any]]:
        branches = super()._branches(birth, subject_id, revision)
        location = birth.get("location", {})
        if not isinstance(location, dict):
            raise ValueError("出生地点结构无效")
        tz = validated_number(birth.get("timezone_offset", location.get("timezone_offset")), "出生时UTC偏移", -14, 14)
        result = []
        for branch in branches:
            value = self._request("jie_probe", {"datetime": branch["civil_datetime"], "tz": tz})
            result.extend(expand(branch, value) if value else [branch])
        return list({row["id"]: row for row in result}.values())

    @staticmethod
    def _derive_bazi(data: dict[str, Any]) -> None:
        # Only the explicit P8 entry bridges the already-documented Si order.
        # The raw engine table remains in p8 provenance; v3 still rejects it.
        expected = {key: list(HIDDEN[row["zhi"]]) for key, row in data["pillars"].items()}
        actual = data.get("hidden_stems", {})
        mismatches = [key for key in expected if actual.get(key) != expected[key]]
        if mismatches and all(
            data["pillars"][key]["zhi"] == "巳" and actual.get(key) == ["丙", "庚", "戊"] for key in mismatches
        ):
            data["p8"]["engine_hidden_stems_before_legacy_derivation"] = deepcopy(actual)
            data["p8"]["legacy_bridge"] = "P8显式入口按v3既有表派生旧字段；新字段使用所选具名表；默认v3未改"
            data["hidden_stems"] = expected
        ChartAdapter._derive_bazi(data)

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
            paths.extend(
                [
                    ("p8.time_interactions", "/data/p8/time_interactions", "layered_decadal_yearly_monthly_daily"),
                    ("p8.rule_hits", "/data/p8/rule_hits", "mixed_natal_and_temporal_conditions"),
                ]
            )
            paths.append(("p8.decade_luck", "/data/p8/decade_luck", "decadal"))
            for key, scale in (
                ("year", "yearly"),
                ("months", "monthly_exact_jie_intervals"),
                ("day", "daily_snapshot"),
            ):
                paths.append(("p8.calendar_layers." + key, "/data/p8/calendar_layers/" + key, scale))
        if system == "ziwei" and "p8_time_interactions" in data:
            paths.append(("p8_time_interactions", "/data/p8_time_interactions", "yearly"))
        if system == "ziwei" and "p8_flying_transformations" in data:
            paths.append(
                (
                    "p8_flying_transformations",
                    "/data/p8_flying_transformations",
                    "layered_natal_decadal_yearly_monthly_daily",
                )
            )
        if system == "astro" and "p8_transit_windows" in data:
            paths.append(("p8_transit_windows", "/data/p8_transit_windows", "transit_interval"))
        return paths
