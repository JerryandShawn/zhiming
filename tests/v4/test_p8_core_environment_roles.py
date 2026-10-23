"""Pure inherited-environment checks; no Git, taskkill, child or collector runs."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from mingjing_core.adapters.charts.benchmarks import line_coverage_core_git as metadata
from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_supervisor as supervisor,
)

FORBIDDEN = (
    "__PYVENV_LAUNCHER__",
    "PYTHONHOME",
    "PYTHONEXECUTABLE",
    "PYTHONPATH",
    "VIRTUAL_ENV",
)
ORDINARY = {
    "SYSTEMROOT": "SYNTHETIC_SYSTEMROOT",
    "TEMP": "SYNTHETIC_TEMP",
    "PATH": "SYNTHETIC_PATH",
    "PYTHONUTF8": "1",
    "PYTHONNOUSERSITE": "1",
}
GIT_FIXED = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
}


@pytest.fixture(params=["metadata_git", "supervisor_taskkill"])
def environment_factory(request) -> Callable[[], dict[str, str]]:
    if request.param == "metadata_git":
        return metadata.safe_environment
    return supervisor._environment


@contextmanager
def inherited_environment(extra: dict[str, str]) -> Iterator[dict[str, str]]:
    # Windows' real os.environ uppercases keys before the function can see them.
    # A plain mapping exercises the real function's case handling on every OS.
    mapping = dict(ORDINARY)
    with patch.object(metadata.os, "environ", mapping), patch.dict(mapping, extra):
        before = dict(mapping)
        yield mapping
        assert mapping == before


def spelling(name: str, style: str) -> str:
    if style == "upper":
        return name
    if style == "lower":
        return name.lower()
    return "".join(
        character.lower() if index % 2 else character.upper()
        for index, character in enumerate(name)
    )


@pytest.mark.parametrize("name", FORBIDDEN)
@pytest.mark.parametrize("style", ["upper", "lower", "mixed"])
def test_launch_context_names_are_removed_case_insensitively(
    name: str, style: str, environment_factory
) -> None:
    inherited_name = spelling(name, style)
    assert inherited_name.upper() == name
    with inherited_environment({inherited_name: "SYNTHETIC_INHERITED_CONTEXT"}):
        result = environment_factory()
        assert all(key.upper() not in FORBIDDEN for key in result)
        assert "SYNTHETIC_INHERITED_CONTEXT" not in result.values()
        for key, value in ORDINARY.items():
            assert result[key] == value


def test_all_five_contexts_are_removed_without_broad_python_filter(
    environment_factory,
) -> None:
    extra = {name: "SYNTHETIC_CONTEXT_" + name for name in FORBIDDEN}
    extra["PYTHONHOME_NOTE"] = "SYNTHETIC_NON_CONTEXT_NOTE"
    with inherited_environment(extra):
        result = environment_factory()
        assert all(key.upper() not in FORBIDDEN for key in result)
        assert result["PYTHONHOME_NOTE"] == "SYNTHETIC_NON_CONTEXT_NOTE"
        for key, value in ORDINARY.items():
            assert result[key] == value


def test_credentials_tracking_and_provider_overrides_remain_filtered(
    environment_factory,
) -> None:
    names = (
        "SYNTHETIC_API_KEY",
        "synthetic_access_token",
        "AppSecret",
        "synthetic_password",
        "CORE_TEST_DSN",
        "DATABASE_URL",
        "langchain_project",
        "LANGSMITH_PROJECT",
        "git_ssh_command",
        "pytest_plugins",
        "Kimi_Base_Url",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
    )
    inherited = {name: "SYNTHETIC_SENSITIVE_" + name for name in names}
    with inherited_environment(inherited):
        result = environment_factory()
        assert not {key.upper() for key in result}.intersection(
            name.upper() for name in names
        )
        assert not set(inherited.values()).intersection(result.values())


def test_git_configuration_remains_fixed_in_both_environment_roles(
    environment_factory,
) -> None:
    inherited = dict.fromkeys(
        (*GIT_FIXED, "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"),
        "SYNTHETIC_UNTRUSTED_GIT_SETTING",
    )
    with inherited_environment(inherited):
        result = environment_factory()
        assert {
            key: value
            for key, value in result.items()
            if key.upper().startswith("GIT_")
        } == GIT_FIXED


def test_supervisor_reuses_real_cleaner_then_pins_plugins_and_tracking() -> None:
    inherited = {name.lower(): "SYNTHETIC_LAUNCH_CONTEXT" for name in FORBIDDEN}
    inherited.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="0",
        PYTEST_ADDOPTS="SYNTHETIC_UNTRUSTED_OPTIONS",
        PYDANTIC_DISABLE_PLUGINS="SYNTHETIC_PLUGIN_SELECTION",
        LANGCHAIN_TRACING_V2="true",
        LANGSMITH_TRACING="true",
    )
    with (
        inherited_environment(inherited),
        patch.object(
            supervisor, "safe_environment", wraps=metadata.safe_environment
        ) as cleaner,
    ):
        result = supervisor._environment()
        cleaner.assert_called_once_with()
        assert all(key.upper() not in FORBIDDEN for key in result)
        assert result["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        assert result["PYTEST_ADDOPTS"] == ""
        assert result["PYDANTIC_DISABLE_PLUGINS"] == "__all__"
        assert result["LANGCHAIN_TRACING_V2"] == "false"
        assert result["LANGSMITH_TRACING"] == "false"


def test_returned_environment_does_not_alias_or_mutate_the_parent_mapping(
    environment_factory,
) -> None:
    original_environment = metadata.os.environ
    with inherited_environment({}) as inherited:
        first = environment_factory()
        second = environment_factory()
        assert first == second and first is not second and first is not inherited
        first["PATH"] = "SYNTHETIC_CHILD_ONLY_PATH"
        assert inherited["PATH"] == second["PATH"] == ORDINARY["PATH"]
    assert metadata.os.environ is original_environment
