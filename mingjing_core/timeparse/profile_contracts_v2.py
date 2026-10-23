"""Explicit trusted profile date projections; no real memory, source text or profile query is included."""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class ProfileScope:
    owner_id: str
    subject_id: str

    def __post_init__(self) -> None:
        if any(type(value) is not str or not value.strip() for value in (self.owner_id, self.subject_id)):
            raise ValueError("profile_scope_required")


@dataclass(frozen=True, repr=False)
class ProfileDateRecord:
    scope: ProfileScope
    key: str
    month: int
    day: int
    source_id: str
    revision: int = 1
    year: int | None = None
    calendar_kind: str = "solar"
    leap_month: bool = False
    active: bool = True
    current: bool = True
    confirmed: bool = False
    revoked: bool = False
    incognito: bool = False
    current_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ProfileScope):
            raise ValueError("profile_scope_required")
        if any(type(value) is not str or not value.strip() for value in (self.key, self.source_id)):
            raise ValueError("profile_identifier_required")
        if self.calendar_kind not in {"solar", "lunar"}:
            raise ValueError("profile_calendar_invalid")
        flags = (self.leap_month, self.active, self.current, self.confirmed, self.revoked, self.incognito)
        if any(type(value) is not bool for value in flags):
            raise ValueError("profile_boolean_required")
        if type(self.month) is not int or type(self.day) is not int or not 1 <= self.month <= 12:
            raise ValueError("profile_date_invalid")
        if self.year is not None and (type(self.year) is not int or not 1 <= self.year <= 9999):
            raise ValueError("profile_year_invalid")
        if self.calendar_kind == "solar":
            if self.leap_month:
                raise ValueError("solar_profile_cannot_have_leap_month")
            date(self.year or 2000, self.month, self.day)
        elif not 1 <= self.day <= 30:
            raise ValueError("profile_lunar_date_invalid")
        if self.current_revision is None:
            object.__setattr__(self, "current_revision", self.revision)
        if any(type(value) is not int or value < 1 for value in (self.revision, self.current_revision)):
            raise ValueError("profile_revision_invalid")


class ProfileDatePort(Protocol):
    def lookup(self, scope: ProfileScope, key: str) -> tuple[ProfileDateRecord, ...]:
        """Host supplies current authenticated source metadata, never model-asserted authorization."""
        ...


@dataclass(frozen=True)
class InMemoryProfileDates:
    records: tuple[ProfileDateRecord, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.records, (tuple, list)) or any(
            not isinstance(item, ProfileDateRecord) for item in self.records
        ):
            raise ValueError("profile_records_invalid")
        object.__setattr__(self, "records", tuple(self.records))

    def lookup(self, scope: ProfileScope, key: str) -> tuple[ProfileDateRecord, ...]:
        return tuple(item for item in self.records if item.scope == scope and item.key == key)
