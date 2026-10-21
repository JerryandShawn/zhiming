"""Bounded chat representation selection; Accept never selects a runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException

NOT_ACCEPTABLE = "请求的响应格式暂不支持，请使用事件流或已配置的 v4 JSON 入口"
_TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
_MEDIA = re.compile(rf"({_TOKEN}|\*)/({_TOKEN}|\*)\Z")
_QUALITY = re.compile(r"(?:0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?)\Z")


def unacceptable() -> HTTPException:
    return HTTPException(
        406, NOT_ACCEPTABLE, headers={"Vary": "Accept", "Cache-Control": "no-store"}
    )


@dataclass(frozen=True)
class ChatAccept:
    ranges: tuple[tuple[str, str, int], ...]

    def representation(self, runtime: str) -> Literal["json", "sse"]:
        stream = self._quality("text", "event-stream")
        # A wildcard does not opt an old client into the new JSON handshake.
        explicit_json = max(
            (
                q
                for first, second, q in self.ranges
                if (first, second) == ("application", "json")
            ),
            default=0,
        )
        if runtime == "v4" and explicit_json > 0 and explicit_json >= stream:
            return "json"
        if stream > 0:
            return "sse"
        raise unacceptable()

    def _quality(self, first: str, second: str) -> int:
        matches = [
            (int(left != "*") + int(right != "*"), quality)
            for left, right, quality in self.ranges
            if left in {"*", first} and right in {"*", second}
        ]
        return max(matches)[1] if matches else 0


def parse_chat_accept(values: list[str]) -> ChatAccept:
    if not values:
        return ChatAccept((("*", "*", 1000),))
    if sum(len(value) for value in values) > 4096:
        raise unacceptable()
    entries = ",".join(values).split(",")
    if len(entries) > 32:
        raise unacceptable()
    return ChatAccept(tuple(_range(entry) for entry in entries))


def _range(entry: str) -> tuple[str, str, int]:
    parts = [part.strip() for part in entry.split(";")]
    match = _MEDIA.fullmatch(parts[0])
    if (
        match is None
        or match[1] == "*"
        and match[2] != "*"
        or any("*" in part and part != "*" for part in match.groups())
    ):
        raise unacceptable()
    quality, seen = 1000, set()
    for parameter in parts[1:]:
        name, separator, value = parameter.partition("=")
        name, value = name.strip().lower(), value.strip()
        if (
            not separator
            or re.fullmatch(_TOKEN, name) is None
            or not value
            or name in seen
        ):
            raise unacceptable()
        seen.add(name)
        if name == "q":
            if _QUALITY.fullmatch(value) is None:
                raise unacceptable()
            quality = int(value.split(".")[0]) * 1000
            quality += int((value.partition(".")[2] + "000")[:3])
        elif re.fullmatch(_TOKEN, value) is None:
            raise unacceptable()
    return match[1].lower(), match[2].lower(), quality
