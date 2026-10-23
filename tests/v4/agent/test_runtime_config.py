"""Trusted repository configuration fails closed before any runtime/provider work."""

from __future__ import annotations

from copy import deepcopy

import pytest

from mingjing_core.agent.loop_policy import LoopPolicy
from mingjing_core.agent.runtime_config import (
    RuntimeConfigError,
    load_runtime_config,
    validate_runtime_config,
)
from mingjing_core.domain.contracts import EvidenceError


def document() -> dict:
    return load_runtime_config().model_dump()


def test_persistent_lane_caps_override_user_depth_without_changing_depth() -> None:
    config = load_runtime_config()
    interactive = config.policy("interactive", "deep")
    background = config.policy("background", "standard")
    assert (interactive.iterations, interactive.seconds, interactive.tools_per_step) == (40, 480, 6)
    assert (background.iterations, background.seconds, background.tools_per_step) == (60, 1200, 10)
    assert interactive.depth == "deep" and background.depth == "standard"
    assert (LoopPolicy(depth="deep").iterations, LoopPolicy().iterations) == (60, 40)


@pytest.mark.parametrize("section,key", [("interactive", "max_iterations"), ("background", "repeat_limit")])
@pytest.mark.parametrize("value", [True, False, -1, 0, 2.0, "2", None])
def test_limits_reject_nonpositive_or_noninteger_fields(section, key, value) -> None:
    raw = document()
    raw[section][key] = value
    with pytest.raises(RuntimeConfigError, match="批准"):
        validate_runtime_config(raw)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("interactive", "max_iterations", 41),
        ("interactive", "max_seconds", 481),
        ("interactive", "max_tools", 7),
        ("background", "max_iterations", 61),
        ("background", "max_seconds", 1201),
        ("background", "max_tools", 11),
        ("background", "repeat_limit", 4),
        (None, "lease_seconds", 151),
        (None, "renew_seconds", 21),
        (None, "version", True),
        (None, "version", 2),
    ],
)
def test_approved_upper_bounds_cannot_be_raised(section, key, value) -> None:
    raw = document()
    (raw if section is None else raw[section])[key] = value
    with pytest.raises(RuntimeConfigError):
        validate_runtime_config(raw)


@pytest.mark.parametrize("section", [None, "interactive", "background"])
def test_unknown_fields_are_not_silently_ignored(section) -> None:
    raw = document()
    (raw if section is None else raw[section])["untrusted_path"] = "sensitive-sentinel"
    with pytest.raises(RuntimeConfigError) as error:
        validate_runtime_config(raw)
    assert "sensitive-sentinel" not in str(error.value)


def test_lower_config_maps_every_key_and_hash_is_canonical() -> None:
    raw = document()
    raw["interactive"] = dict(max_iterations=2, max_seconds=7, max_tools=1, repeat_limit=2)
    raw.update(lease_seconds=15, renew_seconds=3)
    config = validate_runtime_config(raw)
    reordered = validate_runtime_config(dict(reversed(list(deepcopy(raw).items()))))
    policy = config.policy("interactive", "standard", crisis=True)
    assert (policy.iterations, policy.seconds, policy.tools_per_step, policy.repeat_limit) == (2, 7, 1, 2)
    assert (policy.lease_seconds, policy.renew_seconds, policy.text_only) == (15, 3, True)
    assert reordered.sha256 == config.sha256 and len(config.sha256) == 64
    raw["interactive"]["max_iterations"] = 3
    assert validate_runtime_config(raw).sha256 != config.sha256


@pytest.mark.parametrize("lease,renew", [(1, 1), (3, 4), (20, 20), (True, 1), (30, False)])
def test_renewal_must_precede_valid_lease_expiry(lease, renew) -> None:
    raw = document()
    raw.update(lease_seconds=lease, renew_seconds=renew)
    with pytest.raises(RuntimeConfigError):
        validate_runtime_config(raw)


@pytest.mark.parametrize("content", [None, b"not: [yaml", b"version: 1\nversion: 1\n", b"\xff", b"x" * 16385])
def test_locked_path_missing_or_corrupt_never_falls_back(tmp_path, monkeypatch, content) -> None:
    path = tmp_path / "runtime.yaml"
    if content is not None:
        path.write_bytes(content)
    monkeypatch.setattr("mingjing_core.agent.runtime_config.CONFIG_PATH", path)
    with pytest.raises(RuntimeConfigError):
        load_runtime_config()


def test_environment_cannot_replace_repository_config(tmp_path, monkeypatch) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text("sensitive-sentinel", encoding="utf-8")
    monkeypatch.setenv("RUNTIME_CONFIG", str(path))
    monkeypatch.setenv("MINGJING_RUNTIME_CONFIG", str(path))
    assert load_runtime_config().policy("interactive", "deep").iterations == 40
    with pytest.raises(TypeError):
        load_runtime_config(path)


@pytest.mark.parametrize("lane", ["model-declared", "", True])
def test_policy_rejects_unknown_lanes(lane) -> None:
    with pytest.raises(RuntimeConfigError):
        load_runtime_config().policy(lane, "standard")


def test_component_policy_with_lane_cannot_expand_using_depth() -> None:
    with pytest.raises(EvidenceError, match="上限"):
        LoopPolicy(depth="deep", lane="interactive", max_iterations=41)
    assert LoopPolicy(depth="standard", lane="background").iterations == 60
