"""Local controller interpreter and checkpoint SQL evidence; never release authority."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata as metadata
import json
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_contracts import RestoreRejected, digest, ordinary, require
from tools.first_release_incremental import BackupInputs

HERE = Path(__file__)
SAVER_DISTRIBUTION = "langgraph-checkpoint-postgres"
SAVER_FILES = ("langgraph/checkpoint/postgres/__init__.py", "langgraph/checkpoint/postgres/base.py")
_MINT = object()


@dataclass(frozen=True)
class ControllerRuntimePin:
    candidate: str
    manifest_sha256: str
    core_lock_sha256: str
    controller_sha256: str
    python_sha256: str
    saver_version: str
    saver_init_sha256: str
    saver_base_sha256: str
    saver_migrations_sha256: str
    saver_migrations_count: int

    def __post_init__(self) -> None:
        require(digest(self.candidate, 40), "CONTROLLER_CANDIDATE_PIN")
        require(
            all(digest(getattr(self, field)) for field in self.__dataclass_fields__ if field.endswith("sha256")),
            "CONTROLLER_RUNTIME_PIN_DIGEST",
        )
        require(isinstance(self.saver_version, str) and bool(self.saver_version), "CONTROLLER_SAVER_VERSION_PIN")
        require(
            type(self.saver_migrations_count) is int and self.saver_migrations_count > 0,
            "CONTROLLER_SAVER_SQL_COUNT_PIN",
        )

    @classmethod
    def parse(cls, value: dict[str, Any]) -> ControllerRuntimePin:
        fields = set(cls.__dataclass_fields__)
        require(type(value) is dict and set(value) == fields | {"schema"}, "CONTROLLER_RUNTIME_PIN_FIELDS")
        require(value["schema"] == "first-release-controller-runtime-pin-v1", "CONTROLLER_RUNTIME_PIN_SCHEMA")
        return cls(**{name: value[name] for name in fields})


class RuntimeWitness:
    """An opaque process-local observation; JSON and public construction cannot mint it."""

    __slots__ = ("__weakref__",)

    def __new__(cls, seal: object = None) -> RuntimeWitness:
        require(seal is _MINT, "CONTROLLER_RUNTIME_WITNESS_REQUIRED")
        return super().__new__(cls)


@dataclass(frozen=True)
class _Observation:
    backup: BackupInputs
    replay: CandidateReplay
    pin: ControllerRuntimePin
    saver: type[Any]
    summary: dict[str, Any]


_WITNESSES: WeakKeyDictionary[RuntimeWitness, _Observation] = WeakKeyDictionary()


def _sha(path: Path) -> str:
    ordinary(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(backup: BackupInputs, replay: CandidateReplay, pin: ControllerRuntimePin) -> Path:
    require(
        type(backup) is BackupInputs and type(replay) is CandidateReplay and type(pin) is ControllerRuntimePin,
        "CONTROLLER_RUNTIME_TYPED_INPUTS",
    )
    preflight = dict(replay.preflight.pin)
    require(
        backup.local_drill is True
        and (backup.release.candidate, backup.release.manifest_sha256) == (pin.candidate, pin.manifest_sha256)
        and (preflight.get("candidate"), preflight.get("manifest_sha256")) == (pin.candidate, pin.manifest_sha256),
        "CONTROLLER_RUNTIME_CANDIDATE_BINDING",
    )
    require(
        backup.python_sha256 == preflight.get("python_sha256") == pin.python_sha256
        and dict(backup.release.locks).get("requirements-core.lock") == pin.core_lock_sha256,
        "CONTROLLER_RUNTIME_INPUT_BINDING",
    )
    require(_sha(HERE) == pin.controller_sha256, "CONTROLLER_RUNTIME_CODE_CHANGED")
    lock = backup.candidate_source / "requirements-core.lock"
    require(_sha(lock) == pin.core_lock_sha256, "CONTROLLER_CORE_LOCK_CHANGED")
    return lock


def _interpreter(backup: BackupInputs, replay: CandidateReplay, pin: ControllerRuntimePin) -> set[Path]:
    for path in (backup.python, replay.preflight.python, Path(sys.executable)):
        ordinary(path)
    require(
        sys.version_info[:2] == (3, 11)
        and sys.prefix != sys.base_prefix
        and Path(sys.executable).resolve() == backup.python.resolve() == replay.preflight.python.resolve()
        and _sha(Path(sys.executable)) == pin.python_sha256,
        "CONTROLLER_ACTUAL_INTERPRETER",
    )
    prefix = Path(sys.prefix).resolve()
    ordinary(prefix, directory=True)
    sites = {Path(sysconfig.get_path(key)).resolve() for key in ("purelib", "platlib")}
    for site in sites:
        ordinary(site, directory=True)
        require(site.is_relative_to(prefix), "CONTROLLER_VENV_SITE_REQUIRED")
    return sites


def _active_pins(lock: Path) -> tuple[dict[str, str], dict[str, set[str]], dict[str, str]]:
    pins: dict[str, str] = {}
    extras: dict[str, set[str]] = {}
    environment = default_environment()
    for line in lock.read_text(encoding="utf-8").splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        item = Requirement(line.rstrip(" \\"))
        if item.marker and not item.marker.evaluate(environment):
            continue
        name, versions = canonicalize_name(item.name), list(item.specifier)
        require(not item.url and len(versions) == 1 and versions[0].operator == "==", "CONTROLLER_CORE_LOCK_FORMAT")
        version = versions[0].version
        require(name not in pins or pins[name] == version, "CONTROLLER_CORE_LOCK_FORMAT")
        pins[name] = version
        extras.setdefault(name, set()).update(item.extras)
    require(bool(pins), "CONTROLLER_CORE_LOCK_FORMAT")
    return pins, extras, environment


def _dependency_edges(pins: dict[str, str], extras: dict[str, set[str]], environment: dict[str, str]) -> int:
    queue, visited, edges = list(pins), set(), 0
    while queue:
        name = queue.pop()
        enabled = extras.setdefault(name, set())
        signature = name, tuple(sorted(enabled))
        if signature in visited:
            continue
        visited.add(signature)
        for raw in metadata.requires(name) or []:
            item = Requirement(raw)
            if item.marker and not any(
                item.marker.evaluate(dict(environment, extra=extra)) for extra in ("", *enabled)
            ):
                continue
            child_name = canonicalize_name(item.name)
            require(
                not item.url and child_name in pins and pins[child_name] in item.specifier,
                "CONTROLLER_DEPENDENCY_CLOSURE",
            )
            edges += 1
            child = extras.setdefault(child_name, set())
            if item.extras - child:
                child.update(item.extras)
                queue.append(child_name)
    return edges


def _dependencies(lock: Path, sites: set[Path]) -> tuple[dict[str, str], int]:
    pins, extras, environment = _active_pins(lock)
    for name, version in pins.items():
        distribution = metadata.distribution(name)
        require(
            distribution.version == version
            and any(Path(distribution.locate_file("")).resolve().is_relative_to(site) for site in sites),
            "CONTROLLER_ACTIVE_DEPENDENCY",
        )
    return pins, _dependency_edges(pins, extras, environment)


def _module(name: str, sites: set[Path]) -> Any:
    module = importlib.import_module(name)
    spec = module.__spec__
    require(spec is not None and spec.name == name, "CONTROLLER_MODULE_ORIGIN")
    if spec.origin is not None:
        actual = Path(module.__file__)
        ordinary(actual)
        require(
            actual.resolve() == Path(spec.origin).resolve()
            and any(actual.resolve().is_relative_to(site) for site in sites),
            "CONTROLLER_MODULE_ORIGIN",
        )
    if spec.submodule_search_locations is not None:
        require(list(module.__path__) == list(spec.submodule_search_locations), "CONTROLLER_MODULE_ORIGIN")
        require(
            all(any(Path(path).resolve().is_relative_to(site) for site in sites) for path in module.__path__),
            "CONTROLLER_MODULE_ORIGIN",
        )
    return module


def _saver(saver: type[Any], pin: ControllerRuntimePin, pins: dict[str, str], sites: set[Path]) -> None:
    for name in ("packaging", "psycopg", "psycopg_pool", "pydantic", "langgraph", "langgraph.checkpoint"):
        _module(name, sites)
    module = _module("langgraph.checkpoint.postgres", sites)
    base = _module("langgraph.checkpoint.postgres.base", sites)
    require(
        saver is module.PostgresSaver and saver.__module__ == module.__name__ and saver.MIGRATIONS is base.MIGRATIONS,
        "CONTROLLER_ACTUAL_SAVER_REQUIRED",
    )
    distribution = metadata.distribution(SAVER_DISTRIBUTION)
    require(distribution.version == pin.saver_version == pins.get(SAVER_DISTRIBUTION), "CONTROLLER_SAVER_VERSION")
    owned = {str(path).replace("\\", "/") for path in distribution.files or []}
    for name, imported, expected in zip(
        SAVER_FILES, (module, base), (pin.saver_init_sha256, pin.saver_base_sha256), strict=True
    ):
        located = Path(distribution.locate_file(name))
        require(
            name in owned and located.resolve() == Path(imported.__file__).resolve(), "CONTROLLER_SAVER_DISTRIBUTION"
        )
        require(_sha(located) == expected, "CONTROLLER_SAVER_SOURCE_CHANGED")
    require(
        Path(saver.setup.__code__.co_filename).resolve() == Path(module.__file__).resolve(),
        "CONTROLLER_SAVER_SETUP_ORIGIN",
    )
    migrations = saver.MIGRATIONS
    require(
        type(migrations) is list
        and len(migrations) == pin.saver_migrations_count
        and all(type(statement) is str and statement for statement in migrations),
        "CONTROLLER_SAVER_SQL_CHANGED",
    )
    encoded = json.dumps(migrations, ensure_ascii=False, separators=(",", ":")).encode()
    require(hashlib.sha256(encoded).hexdigest() == pin.saver_migrations_sha256, "CONTROLLER_SAVER_SQL_CHANGED")


def _inspect(
    backup: BackupInputs, replay: CandidateReplay, pin: ControllerRuntimePin, saver: type[Any]
) -> dict[str, Any]:
    try:
        lock = _binding(backup, replay, pin)
        sites = _interpreter(backup, replay, pin)
        pins, edges = _dependencies(lock, sites)
        _saver(saver, pin, pins, sites)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, metadata.PackageNotFoundError):
        raise RestoreRejected("CONTROLLER_RUNTIME_INSPECTION_FAILED") from None
    return {
        "schema": "first-release-local-controller-runtime-v1",
        "candidate": pin.candidate,
        "manifest_sha256": pin.manifest_sha256,
        "core_lock_sha256": pin.core_lock_sha256,
        "python_sha256": pin.python_sha256,
        "python_version": sys.version.split()[0],
        "active_core_pins": len(pins),
        "active_dependency_edges": edges,
        "saver_version": pin.saver_version,
        "saver_migrations_count": pin.saver_migrations_count,
        "saver_migrations_sha256": pin.saver_migrations_sha256,
        "controller_runtime_verified": True,
        "wheel_artifacts_verified": False,
        "supply_chain_verified": False,
        "runtime_verified": False,
        "linux_attestation": False,
        "publication": False,
        "database_connections": 0,
        "model_calls": 0,
        "external_sends": 0,
    }


def verify_controller_runtime(
    backup: BackupInputs, replay: CandidateReplay, pin: ControllerRuntimePin, saver_cls: type[Any]
) -> RuntimeWitness:
    summary = _inspect(backup, replay, pin, saver_cls)
    witness = RuntimeWitness(_MINT)
    _WITNESSES[witness] = _Observation(backup, replay, pin, saver_cls, summary)
    return witness


def _observation(witness: RuntimeWitness) -> _Observation:
    require(type(witness) is RuntimeWitness and witness in _WITNESSES, "CONTROLLER_RUNTIME_WITNESS_REQUIRED")
    return _WITNESSES[witness]


def runtime_summary(witness: RuntimeWitness) -> dict[str, Any]:
    """A copied body-free receipt has no authority and cannot be parsed into a witness."""
    return dict(_observation(witness).summary)


def verified_saver(witness: RuntimeWitness) -> type[Any]:
    """Recheck the actual live class and SQL immediately before any future checkpoint stage."""
    observed = _observation(witness)
    require(
        _inspect(observed.backup, observed.replay, observed.pin, observed.saver) == observed.summary,
        "CONTROLLER_RUNTIME_CHANGED_AFTER_OBSERVATION",
    )
    return observed.saver
