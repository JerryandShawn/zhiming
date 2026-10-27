"""Public synthetic experiment inputs reproduce the previously fixed experiment."""

from __future__ import annotations

from mingjing_core.adapters.charts.rectification_workbench.contracts import digest
from mingjing_core.adapters.charts.rectification_workbench.evaluation_cases import (
    PEOPLE,
    fixture_requests,
)


def test_ten_declared_synthetic_people_are_fixed_and_scope_separated() -> None:
    rows = fixture_requests()
    assert len(rows) == len(PEOPLE) == 10
    assert len({row["subject_id"] for row in rows}) == 10
    assert [row["birth"]["date"] for row in rows] == [person[0] for person in PEOPLE]
    assert all(row["subject_id"].startswith("synthetic-") for row in rows)
    assert all(row["as_of_date"] == "2026-10-18" for row in rows)
    assert digest(rows) == digest(fixture_requests())


def test_fixture_requests_are_fresh_objects_and_do_not_drift_after_mutation() -> None:
    expected = digest(fixture_requests())
    value = fixture_requests()
    value[0]["birth"]["place"]["lon"] = 0
    value[0]["birth"]["reported_time"] = "22:00"
    assert digest(fixture_requests()) == expected
