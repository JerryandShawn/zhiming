"""Brain review 23: explicit release gates and interpretation conventions."""

from __future__ import annotations

from typing import Any


def frozen_rectification_state() -> dict[str, Any]:
    return {
        "feature_state": "experimental_frozen",
        "visible_by_default": False,
        "enabled_for_interpretation": False,
        "distinguishable": False,
        "conclusion": "分不出来",
        "selected_candidate": None,
    }


def release_policy() -> dict[str, Any]:
    return {
        "version": "p8-release-policy-23-v1",
        "decision_source": "23_大脑复核_B1计划与命理线.md §二",
        "interpretation": {
            "primary_basis": "true_solar",
            "comparison_basis": "beijing_standard",
            "comparison_utc_offset_minutes": 480,
            "show_comparison_when_results_differ": True,
            "western_astrology_basis": "actual_UTC_unchanged",
        },
        "rectification": {
            "status": "experimental_frozen",
            "visible_by_default": False,
            "enabled_for_interpretation": False,
            "public_tools": [],
            "conclusion": "分不出来",
            "thresholds_relaxed": False,
            "ziwei_added_to_score": False,
            "requires_new_review_before_enablement": True,
        },
    }
