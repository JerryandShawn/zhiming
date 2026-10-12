"""Strict core state contracts. Persisted facts always cite original sources."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Scope(Contract):
    owner_user_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(default='self', min_length=1, max_length=200)
    case_ids: list[str] = Field(default_factory=list, max_length=8)
    conversation_id: str = Field(default='default', min_length=1, max_length=200)


class SourceRef(Contract):
    message_id: str
    version: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=3000)


class SourcePolicy(Contract):
    run_context: bool = Field(default=False, strict=True)
    origin: Literal['current_user','migration','system','unknown'] = 'unknown'


class SourceMessage(Contract):
    id: str
    owner_user_id: str
    subject_id: str = 'self'
    case_ids: list[str] = Field(default_factory=list)
    conversation_id: str = 'default'
    channel: str
    external_id: str | None = None
    source_id: str
    role: Literal['user', 'assistant', 'tool', 'legacy']
    content: str = Field(max_length=200000)
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revision: int = Field(default=1, ge=1)
    status: str = 'active'
    policy: SourcePolicy = Field(default_factory=SourcePolicy)


class Fact(Contract):
    id: str
    owner_user_id: str
    subject_id: str = 'self'
    case_id: str | None = None
    kind: Literal['preference','constraint','profile','background','goal','event','concern','hearsay','hypothesis','correction']
    content: str = Field(max_length=3000)
    source_refs: list[SourceRef]
    assertion_status: Literal['user_asserted','user_confirmed','tool_observation','legacy_unverified'] = 'user_asserted'
    consent: Literal['granted','pending','revoked'] = 'granted'
    status: str = 'active'
    revision: int = 1
    field: str | None = None
    value: Any = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_id: str | None = None
    retention: str = 'until_revoked'


class Case(Contract):
    id: str
    owner_user_id: str
    subject_id: str = 'self'
    title: str = Field(min_length=1, max_length=120)
    state: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: Literal['open','paused','closed','deleted'] = 'open'
    revision: int = 1


class Episode(Contract):
    id: str
    owner_user_id: str
    subject_id: str
    case_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    summary: str
    assertion_status: Literal['derived'] = 'derived'
    revision: int = 1


class MemorySnapshot(Contract):
    owner_user_id: str
    subject_id: str
    case_ids: list[str] = Field(default_factory=list)
    revision: int
    versions: dict[str, int]
    facts: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    profile_conflicts: list[str] = Field(default_factory=list)
    cases: list[dict[str, Any]] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class SaveReceipt(Contract):
    write_status: Literal['saved','pending_confirmation','stopped','deleted','rejected']
    fact_id: str | None = None
    revision: int | None = None
    reason: str = ''


class Run(Contract):
    id: str
    owner_user_id: str
    subject_id: str
    operation_id: str
    request: dict[str, Any]
    status: str
    result: dict[str, Any] | None = None
    attempts: int = 0
    retry_epoch: int = 0
    calls: int = 0
    call_limit: int
    repair_used: bool = False
    state_version: dict[str, int] = Field(default_factory=dict)
    checkpoint: dict[str, Any] = Field(default_factory=dict)


class CoreError(ValueError):
    code = 'CORE_ERROR'


class ScopeError(CoreError, PermissionError):
    code = 'AUTH_SCOPE_ERROR'


class RevisionConflict(CoreError):
    code = 'STALE_INPUT'


class EvidenceError(CoreError):
    code = 'REFERENCE_ERROR'


class BudgetExceeded(CoreError):
    code = 'BUDGET_EXCEEDED'


class LeaseConflict(CoreError):
    code = 'LEASE_CONFLICT'
