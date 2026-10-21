"""Planning and rendering never imply that a candidate has been saved, executed or delivered."""

from dataclasses import dataclass

from .validation import ReflectionError


@dataclass(frozen=True)
class ReflectionEffects:
    model_calls: int = 0
    queue_writes: int = 0
    fact_writes: int = 0
    profile_writes: int = 0
    notifications: int = 0
    deletes: int = 0

    def __post_init__(self) -> None:
        if any(type(getattr(self, name)) is not int or getattr(self, name) != 0 for name in self.__dataclass_fields__):
            raise ReflectionError("effects_must_be_zero")
