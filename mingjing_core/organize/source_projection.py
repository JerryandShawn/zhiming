"""P5b private source projections; caller rebuilds authorized snapshots in its transaction."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime


def instant(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("检索时间需要带时区")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class SourceRef:
    id: str
    revision: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, str)
            or not self.id
            or type(self.revision) is not int
            or self.revision < 1
        ):
            raise ValueError("检索来源引用无效")


@dataclass(frozen=True)
class SearchSource:
    id: str
    owner_id: str
    subject_id: str
    revision: int = 1
    active: bool = True
    redacted: bool = False
    incognito: bool = False
    role: str = "user"
    origin: str = "current_user"

    def __post_init__(self) -> None:
        strings = (self.id, self.owner_id, self.subject_id)
        if not all(isinstance(value, str) and value for value in strings):
            raise ValueError("检索来源状态无效")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("检索来源状态无效")
        if not all(
            type(value) is bool
            for value in (self.active, self.redacted, self.incognito)
        ):
            raise ValueError("检索来源状态无效")
        if self.role not in {"user", "assistant", "tool", "legacy"} or not isinstance(
            self.origin, str
        ):
            raise ValueError("检索来源角色无效")


@dataclass(frozen=True)
class SearchUnit:
    id: str
    owner_id: str
    subject_id: str
    kind: str
    text: str = field(repr=False)
    said_at: datetime
    event_at: datetime | None = None
    origin: str = "user"
    source_refs: tuple[SourceRef, ...] = ()
    fact_id: str | None = None
    valid: bool = True
    deleted: bool = False
    channel: str = "local"
    alias: str | None = None
    category: str = "background"
    inferred: bool = False

    def __post_init__(self) -> None:
        if (
            not self.id
            or not self.owner_id
            or not self.subject_id
            or not isinstance(self.text, str)
        ):
            raise ValueError("检索单元无效")
        if self.kind in {"fact", "event", "fact_event"} and self.origin != "user":
            raise ValueError("助手话语不能作为用户事实")
        if not all(
            type(value) is bool for value in (self.valid, self.deleted, self.inferred)
        ):
            raise ValueError("检索单元状态无效")
        if self.alias is not None and (
            not isinstance(self.alias, str)
            or not re.fullmatch(r"〔m[1-9]\d*〕", self.alias)
        ):
            raise ValueError("检索引用别名无效")
        object.__setattr__(self, "said_at", instant(self.said_at))
        if self.event_at is not None:
            object.__setattr__(self, "event_at", instant(self.event_at))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        if not all(isinstance(ref, SourceRef) for ref in self.source_refs):
            raise ValueError("检索来源引用无效")
        if self.origin == "assistant_claim":
            object.__setattr__(self, "inferred", True)


def source_index(
    owner: str, subject: str, sources: tuple[SearchSource, ...]
) -> dict[str, SearchSource] | None:
    selected = [
        source
        for source in sources
        if source.owner_id == owner and source.subject_id == subject
    ]
    by_id = {source.id: source for source in selected}
    return by_id if len(by_id) == len(selected) else None


def authorized_index(
    unit: SearchUnit, owner: str, subject: str, by_id: dict[str, SearchSource] | None
) -> bool:
    if (
        unit.owner_id != owner
        or unit.subject_id != subject
        or unit.deleted
        or not unit.source_refs
        or by_id is None
    ):
        return False
    current = all(
        (source := by_id.get(ref.id)) is not None
        and source.revision == ref.revision
        and source.active
        and not source.redacted
        and not source.incognito
        for ref in unit.source_refs
    )
    if not current:
        return False
    selected = tuple(by_id[ref.id] for ref in unit.source_refs)
    if unit.kind in {"fact", "event", "fact_event"}:
        return all(
            source.role == "user" and source.origin == "current_user"
            for source in selected
        )
    if unit.kind == "round":
        return tuple(source.role for source in selected) == ("user", "assistant")
    if unit.origin == "assistant_claim":
        return all(source.role == "assistant" for source in selected)
    return True


def authorized(
    unit: SearchUnit, owner: str, subject: str, sources: tuple[SearchSource, ...]
) -> bool:
    return authorized_index(unit, owner, subject, source_index(owner, subject, sources))
