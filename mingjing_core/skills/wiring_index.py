"""Expose bounded system/topic enums and chapter applicability for Agent wiring."""

from __future__ import annotations

from .loader import SkillLibrary


def skill_index() -> dict:
    """Metadata only. Mainline enforces intent, success, crisis and privacy gates."""
    library = SkillLibrary()
    systems = library.catalog["systems"]
    return {
        "version": library.catalog["version"],
        "systems": list(systems),
        "topics_by_system": {
            system: [row["topic"] for row in library.chapters(system)]
            for system in systems
        },
        "chapters": [
            {
                "system": system,
                "topic": row["topic"],
                "question_types": row["question_types"],
                "applicability": row["wiring_applicability"],
                "required_fields": row["required_fields"],
                "pending_fields": row["pending_fields"],
            }
            for system in systems
            for row in library.chapters(system)
        ],
        "visibility_owner": "mainline_agent_tool_assembly",
        "tool_budget": {"maximum_total": 15, "maximum_new_metaphysics_tool": 1},
        "state_writes": 0,
        "model_calls": 0,
    }
