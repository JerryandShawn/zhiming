"""Explicit opt-in worker routing, separate from the default v3 dispatcher."""

from __future__ import annotations

from typing import Any

PURE_TOOLS = ("daily_transit", "window_search", "almanac", "synastry")


def calculate_pure_tool(system: str, args: dict) -> dict[str, Any]:
    if system == "daily_transit":
        from .daily_transit import daily_transit

        return daily_transit(
            args["natal"], args["date"], orb_degrees=args.get("orb_degrees", 2.0)
        )
    if system == "window_search":
        from .window_search import window_search

        return window_search(
            args["natal"],
            args["range"],
            args["purpose"],
            offset=args.get("offset", 0),
            limit=args.get("limit", 31),
        )
    if system == "almanac":
        from .almanac import almanac

        return almanac(args["date"])
    if system == "synastry":
        from .synastry import synastry

        return synastry(
            args["chart_a"],
            args["chart_b"],
            args["kind"],
            consent=args.get("consent"),
            as_of_date=args["as_of_date"],
            orb_degrees=args.get("orb_degrees", 6.0),
        )
    raise ValueError("p8_pure_tool_unknown")
