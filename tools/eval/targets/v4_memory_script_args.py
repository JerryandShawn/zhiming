"""Translate legacy scripted query selection to real scoped tool arguments; scores stay unchanged."""

from __future__ import annotations

from typing import Any


def adapt_memory_script_args(data: dict[str, Any]) -> None:
    for step in data["scripted"]:
        for action in step["model"]:
            call = action.get("tool_call", {})
            args = call.get("arguments", {})
            if call.get("name") != "memory_forget" or "query" not in args:
                continue
            if not isinstance(args["query"], str) or not args["query"] or args.get("scope") != "all_derived":
                raise ValueError("Legacy forget script must select one declared literal topic")
            matches = [fact for fact in data["seed"].get("facts", []) if args["query"] in fact.get("quote", "")]
            if len(matches) != 1:
                raise ValueError("Legacy forget script has no unique declared target")
            call["arguments"] = {"message_id": f"turn-{step['turn']}", "fact_id": matches[0]["id"]}
