"""One strict read projection for legacy core3 and frozen public core4 results."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from mingjing_core.agent.envelope import validated_result
from mingjing_core.agent.event_contracts import EnvelopeV1
from mingjing_core.domain.contracts import EvidenceError


def read_result(value: Any) -> dict[str, Any]:
    if not validated_result(value):
        raise EvidenceError("结果尚未通过提交校验")
    result = deepcopy(value)
    if result["schema_version"] == "core3.0":
        result["text"] = result["answer"]
        return result
    try:
        validated = EnvelopeV1.model_validate(result).model_dump(by_alias=True, exclude_unset=True)
    except (ValidationError, ValueError, TypeError):
        raise EvidenceError("core4结果格式不符") from None
    validated["answer"] = validated["text"]
    return validated
