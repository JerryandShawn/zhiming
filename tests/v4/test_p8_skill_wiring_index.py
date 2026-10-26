"""32 chapter pairs remain allowlisted and contain explicit activation limits."""

from __future__ import annotations

from mingjing_core.skills import SkillLibrary
from mingjing_core.skills.wiring_index import skill_index


def test_index_is_complete_and_metadata_only() -> None:
    index = skill_index()
    assert len(index["chapters"]) == 32
    assert set(index["systems"]) == {
        "bazi",
        "ziwei",
        "astro",
        "tarot",
        "calendar-tools",
    }
    library = SkillLibrary()
    for row in index["chapters"]:
        assert row["topic"] in index["topics_by_system"][row["system"]]
        policy = row["applicability"]
        assert policy["after_successful_chart_compute"] is True
        assert policy["skill_incognito_allowed"] is True
        assert policy["enforcement_owner"] == "mainline"
        assert row["question_types"]
        assert (
            library.load(row["system"], row["topic"])["metadata"][
                "wiring_applicability"
            ]
            == policy
        )
    assert all("text" not in row for row in index["chapters"])


def test_frozen_and_unsupported_topics_never_claim_execution_authority() -> None:
    index = skill_index()
    frozen = [
        row
        for row in index["chapters"]
        if "rectification" in row["topic"] or row["topic"] == "traditional-hour-methods"
    ]
    assert len(frozen) == 3
    assert all(
        row["applicability"]["execution"] == "frozen_refusal_only" for row in frozen
    )
    returns = next(
        row
        for row in index["chapters"]
        if row["system"] == "astro" and row["topic"] == "returns"
    )
    assert returns["applicability"]["execution"] == "educational_only_not_wired"
    for row in index["chapters"]:
        if row["system"] == "calendar-tools":
            assert row["applicability"]["underlying_tool_hidden_in"] == [
                "crisis",
                "incognito",
            ]
            assert row["applicability"]["intent_required"] == row["topic"].replace(
                "-", "_"
            )
