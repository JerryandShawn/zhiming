"""Fixed synthetic people, declared before evaluation; no actual birth records."""

from __future__ import annotations

from typing import Any

PEOPLE = (
    ("1960-06-15", "男"),
    ("1962-11-21", "女"),
    ("1964-02-12", "男"),
    ("1966-07-23", "女"),
    ("1968-01-16", "男"),
    ("1970-09-19", "女"),
    ("1972-04-12", "男"),
    ("1974-12-22", "女"),
    ("1976-05-17", "男"),
    ("1978-08-26", "女"),
)


def fixture_requests() -> list[dict[str, Any]]:
    return [
        {
            "owner_user_id": "synthetic-workbench-owner",
            "subject_id": f"synthetic-actual-chart-{index + 1:02}",
            "operation_id": f"synthetic-grid-{index + 1}",
            "revision": 1,
            "as_of_date": "2026-10-18",
            "birth": {
                "date": day,
                "reported_time": "00:00",
                "gender": gender,
                "place": {"tz": "Asia/Shanghai", "lon": 120, "lat": 30},
                "clock_basis": "standard",
                "precision": "reported",
            },
        }
        for index, (day, gender) in enumerate(PEOPLE)
    ]
