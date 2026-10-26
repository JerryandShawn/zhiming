"""P8-only source annotations leave the shared legacy candidate table intact."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...calculations.bazi.elements import table


def reviewed_climate(climate: dict[str, Any]) -> dict[str, Any]:
    """Annotate the selected opening excerpt without replacing its stem values."""
    output = deepcopy(climate)
    review = table("climate_review_24")
    output["source_review_version"] = review["version"]
    output["table_limits"] = [*output["table_limits"], *review["limitations"]]
    key = output["day_master"] + output["month_branch"]
    if key in review["rows"]:
        output["source_review_24"] = deepcopy(review["rows"][key])
    return output
