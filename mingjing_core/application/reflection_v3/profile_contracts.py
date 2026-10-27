"""A profile item needs an explicit owner/version document and current fact/source anchors."""

from dataclasses import dataclass, field
from datetime import datetime

from mingjing_core.memory2.contracts import MemoryScope, SourceAnchor
from mingjing_core.memory2.reflection import ProfileItem

from .effects import ReflectionEffects
from .validation import ReflectionError, booleans, identities, instant, integer, opaque, typed_tuple


@dataclass(frozen=True)
class ProfileEntry:
    scope: MemoryScope
    item: ProfileItem = field(repr=False)
    revision: int
    anchors: tuple[SourceAnchor, ...] = field(default=(), repr=False)
    origin: str = "user_fact"
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope) or not isinstance(self.item, ProfileItem):
            raise ReflectionError("profile_entry_required")
        opaque(self.item.id)
        integer(self.revision, 1)
        booleans(self.active)
        if type(self.origin) is not str or self.origin not in {"user_fact", "analysis", "chart_unverified"}:
            raise ReflectionError("profile_origin_invalid")
        if len(self.item.text) > 4000:
            raise ReflectionError("profile_text_too_long")
        object.__setattr__(self, "anchors", typed_tuple(self.anchors, SourceAnchor))


@dataclass(frozen=True)
class ProfileDocument:
    scope: MemoryScope
    revision: int
    snapshot_revision: int
    source_epoch: int
    entries: tuple[ProfileEntry, ...] = field(default=(), repr=False)
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("profile_scope_required")
        for value in (self.revision, self.snapshot_revision, self.source_epoch):
            integer(value)
        booleans(self.active)
        object.__setattr__(self, "entries", typed_tuple(self.entries, ProfileEntry))
        if len({row.item.id for row in self.entries}) != len(self.entries):
            raise ReflectionError("duplicate_profile_item")


@dataclass(frozen=True)
class ProfileLine:
    item_id: str
    section: int
    text: str = field(repr=False)
    origin: str
    source_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    anchors: tuple[SourceAnchor, ...] = field(repr=False)
    confidence: float
    pinned: bool
    edited_by_user: bool

    def __post_init__(self) -> None:
        opaque(self.item_id)
        integer(self.section, 1)
        if self.section > 8 or self.origin not in {"user_fact", "analysis"}:
            raise ReflectionError("profile_line_section_or_origin_invalid")
        if type(self.text) is not str or not self.text.strip() or len(self.text) > 4000:
            raise ReflectionError("profile_line_text_invalid")
        booleans(self.pinned, self.edited_by_user)
        if type(self.confidence) not in {int, float} or not 0 <= self.confidence <= 1:
            raise ReflectionError("profile_confidence_invalid")
        object.__setattr__(self, "source_ids", identities(self.source_ids))
        object.__setattr__(self, "fact_ids", identities(self.fact_ids))
        object.__setattr__(self, "anchors", typed_tuple(self.anchors, SourceAnchor))


@dataclass(frozen=True)
class AboutMeSection:
    number: int
    title: str
    lines: tuple[ProfileLine, ...] = field(repr=False)

    def __post_init__(self) -> None:
        from mingjing_core.memory2.reflection import SECTION_TITLES

        integer(self.number, 1)
        if self.number not in SECTION_TITLES or self.title != SECTION_TITLES[self.number]:
            raise ReflectionError("profile_section_invalid")
        object.__setattr__(self, "lines", typed_tuple(self.lines, ProfileLine))
        if any(row.section != self.number for row in self.lines):
            raise ReflectionError("profile_section_line_mismatch")


@dataclass(frozen=True)
class AboutMeView:
    scope: MemoryScope
    profile_revision: int
    snapshot_revision: int
    source_epoch: int
    generated_at: datetime
    sections: tuple[AboutMeSection, ...] = field(repr=False)
    markdown: str = field(repr=False)
    omitted_item_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    effects: ReflectionEffects = ReflectionEffects()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("profile_scope_required")
        object.__setattr__(self, "generated_at", instant(self.generated_at))
        object.__setattr__(self, "sections", typed_tuple(self.sections, AboutMeSection))
        if tuple(row.number for row in self.sections) != tuple(range(1, 9)):
            raise ReflectionError("eight_sections_required")
        if not isinstance(self.effects, ReflectionEffects):
            raise ReflectionError("effects_must_be_zero")
        for value in (self.profile_revision, self.snapshot_revision, self.source_epoch):
            integer(value)
        object.__setattr__(self, "omitted_item_ids", identities(self.omitted_item_ids, minimum=0))
        object.__setattr__(self, "warnings", typed_tuple(self.warnings, str))
