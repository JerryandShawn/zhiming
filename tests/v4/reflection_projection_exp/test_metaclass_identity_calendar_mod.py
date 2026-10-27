"""Unknown classes must stay rejected even when their metaclass spoofs equality and a registry hash."""

from typing import Any

import pytest

from mingjing_core.application.reflection_projection_exp import ProjectionError, project_json, projection_fingerprint
from mingjing_core.application.reflection_v3.validation import dataclass_json, digest
from mingjing_core.memory2.contracts import MemoryScope


class ScalarEqualitySpoof(type):
    __hash__ = type.__hash__

    def __eq__(cls, other: object) -> bool:
        return other is str


class UnknownScalar(metaclass=ScalarEqualitySpoof):
    __slots__ = ()


class RegisteredEqualitySpoof(type):
    def __hash__(cls) -> int:
        return hash(MemoryScope)

    def __eq__(cls, other: object) -> bool:
        return other is MemoryScope


class UnknownScope(metaclass=RegisteredEqualitySpoof):
    owner_id = "synthetic-owner"
    subject_id = "synthetic-subject"


class ContainerEqualitySpoof(type):
    __hash__ = type.__hash__

    def __eq__(cls, other: object) -> bool:
        return other is list


class UnknownContainer(metaclass=ContainerEqualitySpoof):
    def __iter__(self) -> Any:
        return iter(([],))


@pytest.mark.parametrize("value", (UnknownScalar(), UnknownScope(), UnknownContainer()))
def test_unknown_class_cannot_enter_exact_type_projection(value: object) -> None:
    assert type(value) is not str and type(value) is not MemoryScope and type(value) is not list
    with pytest.raises(ValueError):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        project_json(value)


@pytest.mark.parametrize("value", (UnknownScalar(), UnknownScope(), UnknownContainer()))
def test_unknown_class_cannot_gain_a_new_fingerprint_acceptance_path(value: object) -> None:
    with pytest.raises(ValueError):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        projection_fingerprint(value)
