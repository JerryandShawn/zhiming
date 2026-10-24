"""Metadata-model coverage is deliberately not Linux or wheel-integrity evidence."""

from __future__ import annotations

import stat
from dataclasses import replace
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
from b1_runtime_trust_support import BASE, valid_metadata

from tools import b1_runtime_trust as trust


def test_synthetic_posix_success_never_attests_linux_or_package_content() -> None:
    model = valid_metadata()
    result = trust.inspect_metadata(model)
    assert result["entries_checked"] > 15 and result["symlinks_checked"] == 4
    assert len(result["metadata_sha256"]) == 64
    assert result["linux_filesystem_observed"] is result["package_content_verified"] is False
    assert result["stage_acceptance"] is result["publication"] is result["system_site_packages"] is False
    assert model.config_reads == [trust.CONFIG]
    assert "synthetic_pkg" not in str(result) and "protected.pth" not in str(result)


def test_complete_metadata_digest_is_stable_without_reading_package_bytes() -> None:
    first, second = valid_metadata(), valid_metadata()
    second.entries = dict(reversed(list(second.entries.items())))
    assert trust.inspect_metadata(first) == trust.inspect_metadata(second)
    second.entries[trust.PACKAGES / "protected.pth"] = replace(
        second.entries[trust.PACKAGES / "protected.pth"], size=100
    )
    assert (
        trust.inspect_metadata(valid_metadata())["metadata_sha256"] != trust.inspect_metadata(second)["metadata_sha256"]
    )


@pytest.mark.parametrize("path", [PurePosixPath("/"), PurePosixPath("/root"), trust.CORE.parent])
@pytest.mark.parametrize("change", [{"uid": 1000}, {"mode": stat.S_IFDIR | 0o775}])
def test_every_ancestor_must_be_root_owned_and_not_writable(path: PurePosixPath, change: dict) -> None:
    model = valid_metadata()
    model.entries[path] = replace(model.entries[path], **change)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_ANCESTOR_WRITABLE"):
        trust.inspect_metadata(model)
    assert not model.config_reads


@pytest.mark.parametrize(
    "path",
    [
        trust.CONFIG,
        trust.PACKAGES / "protected.pth",
        trust.PACKAGES / "synthetic_pkg/__init__.py",
        trust.PACKAGES / "synthetic_pkg-1.dist-info/METADATA",
    ],
)
@pytest.mark.parametrize("change", [{"uid": 1000}, {"mode": stat.S_IFREG | 0o664}])
def test_package_and_config_leaf_protection_is_not_just_interpreter_metadata(path: PurePosixPath, change: dict) -> None:
    model = valid_metadata()
    model.entries[path] = replace(model.entries[path], **change)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_NOT_ROOT_OWNED|VENV_GROUP_OR_OTHER_WRITABLE"):
        trust.inspect_metadata(model)


@pytest.mark.parametrize(
    "text",
    [
        "include-system-site-packages=true\n",
        "home=/protected/bin\n",
        "include-system-site-packages=false\ninclude-system-site-packages=false\n",
    ],
)
def test_configuration_cannot_enable_or_ambiguously_disable_system_site_packages(text: str) -> None:
    model = valid_metadata()
    model.text = text
    model.entries[trust.CONFIG] = replace(model.entries[trust.CONFIG], size=len(text.encode()))
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_SYSTEM_SITE_PACKAGES"):
        trust.inspect_metadata(model)


def test_oversized_configuration_is_rejected_without_reading_it() -> None:
    model = valid_metadata()
    model.entries[trust.CONFIG] = replace(model.entries[trust.CONFIG], size=trust.MAX_CONFIG_BYTES + 1)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_CONFIG_SCOPE"):
        trust.inspect_metadata(model)
    assert not model.config_reads


def test_nonstandard_adjacent_configuration_is_rejected_without_reading_either_config() -> None:
    model = valid_metadata()
    model.file(trust.CORE / "bin/pyvenv.cfg")
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_CONFIG_SHADOW"):
        trust.inspect_metadata(model)
    assert not model.config_reads


def test_physical_reader_has_no_general_library_content_read_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("non-config content reached open")

    monkeypatch.setattr(trust.os, "open", forbidden)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_CONFIG_SCOPE"):
        trust.ReadOnlyFilesystem().config(trust.PACKAGES / "protected.pth", trust.Entry(stat.S_IFREG | 0o644, 0))


@pytest.mark.parametrize("path", [trust.CONFIG, trust.PACKAGES / "protected.pth", trust.PACKAGES / "alias"])
def test_only_finitely_allowlisted_symlink_positions_are_accepted(path: PurePosixPath) -> None:
    model = valid_metadata()
    model.symlink(path, str(BASE))
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_SYMLINK_NOT_ALLOWED"):
        trust.inspect_metadata(model)


def test_normal_mode777_root_interpreter_links_are_allowed_but_foreign_owner_is_not() -> None:
    model = valid_metadata()
    assert stat.S_IMODE(model.entries[trust.PYTHON].mode) == 0o777
    assert trust.inspect_metadata(model)["symlinks_checked"] == 4
    model.entries[trust.PYTHON] = replace(model.entries[trust.PYTHON], uid=1000)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_NOT_ROOT_OWNED"):
        trust.inspect_metadata(model)


def test_lib64_alias_must_resolve_to_core_lib_without_visiting_charts() -> None:
    model = valid_metadata()
    model.symlink(trust.CORE / "lib64", "../charts/lib")
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_LIB64_TARGET"):
        trust.inspect_metadata(model)
    assert not any(path.is_relative_to(trust.RELEASE / "venv/charts") for path in model.reads)


def test_core_interpreter_cannot_borrow_chart_runtime_or_visit_its_metadata() -> None:
    model = valid_metadata()
    model.symlink(trust.PYTHON, str(trust.RELEASE / "venv/charts/bin/python"))
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_INTERPRETER_SCOPE"):
        trust.inspect_metadata(model)
    assert not any(path.is_relative_to(trust.RELEASE / "venv/charts") for path in model.reads)


@pytest.mark.parametrize("path", [BASE, BASE.parent])
def test_external_interpreter_and_its_ancestors_must_also_be_protected(path: PurePosixPath) -> None:
    model = valid_metadata()
    model.entries[path] = replace(model.entries[path], mode=model.entries[path].mode | 0o002)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_ANCESTOR_WRITABLE|VENV_GROUP_OR_OTHER_WRITABLE"):
        trust.inspect_metadata(model)


def test_interpreter_link_cycle_fails_closed() -> None:
    model = valid_metadata()
    model.symlink(trust.CORE / "bin/python3", "python")
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_LINK_CYCLE"):
        trust.inspect_metadata(model)


def test_too_many_external_interpreter_links_fail_closed() -> None:
    model = valid_metadata()
    for index in range(trust.MAX_LINKS + 1):
        model.symlink(BASE.parent / f"link{index}", str(BASE.parent / f"link{index + 1}"))
    model.symlink(trust.PYTHON, str(BASE.parent / "link0"))
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_LINK_LIMIT"):
        trust.inspect_metadata(model)


def test_unreadable_or_dangling_interpreter_diagnostic_never_leaks() -> None:
    model = valid_metadata()
    model.symlink(trust.PYTHON, "/opt/missing/SYNTHETIC_PRIVATE_PATH")
    with pytest.raises(trust.RuntimeTrustRejected) as error:
        trust.inspect_metadata(model)
    assert str(error.value) == "VENV_METADATA_READ"


def test_special_file_is_rejected_without_opening_it() -> None:
    model = valid_metadata()
    path = trust.PACKAGES / "protected.pth"
    model.entries[path] = replace(model.entries[path], mode=stat.S_IFIFO | 0o600)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_SPECIAL_FILE"):
        trust.inspect_metadata(model)


def test_entry_limit_prevents_partial_tree_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trust, "MAX_ENTRIES", 3)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_METADATA_LIMIT"):
        trust.inspect_metadata(valid_metadata())


def test_physical_directory_reader_stops_during_scan_before_unbounded_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Scan:
        yielded = 0
        closed = False

        def __enter__(self):
            return iter(self)

        def __exit__(self, *args):
            self.closed = True

        def __iter__(self):
            for index in range(10):
                self.yielded += 1
                yield SimpleNamespace(name=f"entry{index}")

    scan = Scan()
    monkeypatch.setattr(trust, "MAX_ENTRIES", 3)
    monkeypatch.setattr(trust.os, "scandir", lambda path: scan)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_DIRECTORY_LIMIT"):
        trust.ReadOnlyFilesystem().names(trust.CORE)
    assert scan.yielded == 4 and scan.closed


def test_model_reader_large_directory_is_rejected_before_duplicate_set_or_pending(monkeypatch) -> None:
    model = valid_metadata()
    monkeypatch.setattr(trust, "MAX_ENTRIES", 12)
    model.names = lambda path: ("duplicate",) * 13
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_DIRECTORY_LIMIT"):
        trust.inspect_metadata(model)


def test_pending_directory_members_are_also_bounded(monkeypatch) -> None:
    model = valid_metadata()
    original = model.names
    model.names = (
        lambda path: tuple(f"entry{index}" for index in range(20)) if path == trust.CORE / "lib" else original(path)
    )
    monkeypatch.setattr(trust, "MAX_ENTRIES", 20)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_DIRECTORY_LIMIT"):
        trust.inspect_metadata(model)


def test_directory_depth_and_duplicate_names_are_rejected() -> None:
    model = valid_metadata()
    model.directory(trust.CORE.joinpath(*["nested"] * 66))
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_DIRECTORY_DEPTH"):
        trust.inspect_metadata(model)
    model = valid_metadata()
    model.duplicate_directory = trust.CORE
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_DIRECTORY_DUPLICATE"):
        trust.inspect_metadata(model)


def test_metadata_change_during_scan_is_not_a_complete_trust_observation() -> None:
    model = valid_metadata()
    model.change_on_repeat = trust.PACKAGES / "protected.pth"
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_METADATA_CHANGED"):
        trust.inspect_metadata(model)


def test_finite_link_targets_are_rechecked_even_if_model_lstat_is_unchanged() -> None:
    model = valid_metadata()
    model.change_link_on_repeat = trust.CORE / "lib64"
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_LINK_CHANGED"):
        trust.inspect_metadata(model)


def test_permission_error_is_body_free() -> None:
    model = valid_metadata()
    model.failed_entry = trust.PACKAGES / "protected.pth"
    with pytest.raises(trust.RuntimeTrustRejected) as error:
        trust.inspect_metadata(model)
    assert str(error.value) == "VENV_METADATA_READ"


def test_physical_entrypoint_rejects_nonlinux_before_constructing_any_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trust, "_linux_host", lambda: False)

    def forbidden():
        pytest.fail("non-Linux host crossed physical metadata boundary")

    monkeypatch.setattr(trust, "ReadOnlyFilesystem", forbidden)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_LINUX_REQUIRED"):
        trust.inspect_core_venv()
