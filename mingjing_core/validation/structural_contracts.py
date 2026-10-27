"""Controlled findings and trusted caller-supplied material for deterministic checks."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mingjing_core.timekit.clock import Clock


@dataclass(frozen=True)
class StructuralContext:
    clock: Clock
    timezone: str = "Asia/Shanghai"
    aliases: frozenset[str] = frozenset()
    receipts: tuple[Mapping[str, Any], ...] = field(default=(), repr=False)
    ask_user_calls: int = 0
    last_model_text: str = field(default="", repr=False)
    farewell: bool = False
    critic_available: bool = True


@dataclass(frozen=True)
class StructuralFinding:
    code: str
    item: str | None
    severity: int
    quote: str = field(repr=False)
    rule: str = ""
    evidence: str = field(default="", repr=False)
    fix_hint: str = ""
    span: tuple[int, int] | None = None


@dataclass(frozen=True)
class StructuralResult:
    text: str = field(repr=False)
    findings: tuple[StructuralFinding, ...]
    ask_user_allowed: bool
