"""Request-only K3 safety checks; no I/O, credentials or persistent quota state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from .errors import CapabilityError, ModelBadRequest, ModelPayloadTooLarge
from .port import ToolSpec

DEFAULT_MAX_REQUEST_BYTES = 1_800_000


def is_k3(model: str) -> bool:
    return model.strip().casefold().startswith(("k3", "kimi-k3"))


def safe_tool_choice(model: str, tools: Sequence[ToolSpec] | None, choice: str) -> str:
    """Keep other providers' choices; K3 must never use none or a named tool."""
    if not is_k3(model):
        return choice
    if choice not in {"auto", "required"}:
        raise CapabilityError()
    return "required" if tools and len(tools) == 1 else choice


def sampling_body(body: dict[str, Any], caps: Mapping[str, Any]) -> dict[str, Any]:
    """A fixed-sampling capability overrides both caller and configured values."""
    if not caps.get("sampling_fixed"):
        return body
    return {key: value for key, value in body.items() if key not in {"temperature", "top_p"}}


def check_request_size(request: httpx.Request, *, model: str, settings: Mapping[str, Any]) -> None:
    """Use the K3 default or an explicit portable-provider limit before charging."""
    if "max_request_bytes" not in settings and not is_k3(model):
        return
    maximum = settings.get("max_request_bytes", DEFAULT_MAX_REQUEST_BYTES)
    if type(maximum) is not int or maximum <= 0:
        raise ModelBadRequest()
    if len(request.content) > maximum:
        raise ModelPayloadTooLarge()
