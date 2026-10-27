"""Explicit 12-midpoint synthetic grid for offline tests, not a user-time solver."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..adapter import stable_id
from ..interactions_ziwei import yearly_mutagen_links
from ..time_basis import time_basis_candidates
from ..time_basis_chart import bazi_context, ziwei_column
from ..time_basis_request import validate_request
from ..worker import load_engine


def _ziwei_years(
    candidate: dict[str, Any], gender: str, years: range, as_of_date: str
) -> dict[str, Any]:
    engine = load_engine("ziwei")
    ast, corrected = engine.build(
        datetime.fromisoformat(candidate["coordinate_datetime"]), 0, gender, 0
    )
    natal = engine.natal(ast, corrected)
    from lunar_python import Lunar

    columns = {}
    for year in years:
        new_year = datetime.fromisoformat(
            Lunar.fromYmd(year, 1, 1).getSolar().toYmdHms()
        )
        left = datetime(year, 1, 1)
        right = min(
            datetime(year + 1, 1, 1),
            datetime.fromisoformat(as_of_date) + timedelta(days=1),
        )
        points = sorted({left, right, *([new_year] if left < new_year < right else [])})
        samples = []
        for start, end in zip(points[:-1], points[1:], strict=True):
            if start == end:
                continue
            sample = (start + (end - start) / 2).date().isoformat()
            layer = engine.scope(ast.horoscope(sample).yearly)
            links = yearly_mutagen_links(
                dict(natal, horoscope={"target_date": sample, "yearly": layer})
            )
            samples.append(
                {
                    "sample_date": sample,
                    "not_event_date": True,
                    "yearly": layer,
                    "mutagen_links": links,
                    "start": start.date().isoformat(),
                    "end_exclusive": end.date().isoformat(),
                }
            )
        columns[str(year)] = samples
    return {
        "natal": ziwei_column(candidate, gender),
        "annual": columns,
        "scored": False,
        "partition": "Gregorian year split at lunar new year, clipped to Clock as_of_date; separate unweighted column",
    }


def synthetic_chart_grid(
    request: dict[str, Any], *, basis: str = "standard"
) -> list[dict[str, Any]]:
    if basis not in ("standard", "true_solar"):
        raise ValueError("synthetic_grid_requires_explicit_registered_basis")
    birth = request["birth"]
    if (
        not request["subject_id"].startswith("synthetic-")
        or birth.get("precision") != "reported"
    ):
        raise ValueError("offline_grid_only_accepts_explicitly_synthetic_requests")
    validate_request(request)
    years = range(int(birth["date"][:4]) + 6, int(request["as_of_date"][:4]) + 1)
    if not years:
        raise ValueError("synthetic_grid_needs_at_least_six_years_of_history")
    contexts = []
    for hour in range(0, 24, 2):
        time = f"{hour:02}:00"
        result = time_basis_candidates(
            birth["date"], time, birth["place"], birth["clock_basis"]
        )
        rows = [
            variant
            for item in result["items"]
            for variant in item["source_variants"]
            if variant["basis"] == basis
        ]
        if len(rows) != 1:
            raise ValueError("synthetic_grid_has_gap_fold_or_unresolved_clock_basis")
        candidate = rows[0]
        data = bazi_context(candidate, request)
        scope = {
            key: request[key] for key in ("owner_user_id", "subject_id", "revision")
        }
        ziwei = _ziwei_years(candidate, birth["gender"], years, request["as_of_date"])
        contexts.append(
            dict(
                scope,
                id=stable_id("grid-", [scope, basis, time]),
                label=f"{basis}:{time}",
                pillars=candidate["pillars"],
                p8=data["p8"],
                data=data,
                time_basis=candidate,
                engine_versions=dict(
                    candidate["engine_versions"], ziwei=ziwei["natal"]["versions"]
                ),
                ziwei_column=ziwei,
                as_of_date=request["as_of_date"],
                grid_limit="12 declared standard-clock midpoints only; not continuous unknown-time coverage",
            )
        )
    return contexts
