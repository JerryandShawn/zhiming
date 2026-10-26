"""Pre/post fixed source and actual Core runtime content fingerprints."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import sys
from pathlib import Path

from .line_coverage_core_git import CONFIGS, MetadataGit
from .line_coverage_manifest import ROOT, digest, normalized
from .line_coverage_own_inventory import validate_own_inventory
from .line_coverage_own_sources import raw_sources

PACKAGES = {
    "pytest": ("pytest", "_pytest"),
    "pluggy": ("pluggy",),
    "iniconfig": ("iniconfig",),
    "packaging": ("packaging",),
    "Pygments": ("pygments",),
    "colorama": ("colorama",),
    "pydantic": ("pydantic",),
    "pydantic_core": ("pydantic_core",),
    "annotated-types": ("annotated_types",),
    "typing-inspection": ("typing_inspection",),
    "typing_extensions": ("typing_extensions.py",),
}
CORE = ROOT.parent / "zhiming-v4/.venv-core/Scripts/python.exe"
FLAGS = (
    "debug",
    "inspect",
    "interactive",
    "optimize",
    "dont_write_bytecode",
    "no_user_site",
    "no_site",
    "ignore_environment",
    "verbose",
    "bytes_warning",
    "quiet",
    "hash_randomization",
    "isolated",
    "dev_mode",
    "utf8_mode",
    "warn_default_encoding",
    "safe_path",
    "int_max_str_digits",
)


def launch_metadata() -> dict:
    actual = {name: getattr(sys.flags, name) for name in FLAGS}
    zeros = (
        "debug",
        "inspect",
        "interactive",
        "optimize",
        "verbose",
        "bytes_warning",
        "quiet",
        "dev_mode",
        "warn_default_encoding",
    )
    ones = (
        "dont_write_bytecode",
        "no_user_site",
        "no_site",
        "ignore_environment",
        "isolated",
        "hash_randomization",
        "safe_path",
    )
    prefix = sys.orig_argv[1:5]
    if (
        any(actual[name] != 0 for name in zeros)
        or any(actual[name] != 1 for name in ones)
        or prefix != ["-I", "-S", "-B", "-X"]
    ):
        raise ValueError("b1_noncanonical_launch_flags")
    if len(sys.orig_argv) < 7 or sys.orig_argv[5] != "pycache_prefix=" + str(
        sys.pycache_prefix
    ):
        raise ValueError("b1_noncanonical_cache_option")
    expected = (
        ROOT
        / "mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py"
    )
    if Path(sys.orig_argv[6]).resolve() != expected.resolve():
        raise ValueError("b1_fixed_bootstrap_entrypoint_required")
    return {"flags": actual, "xoptions": {"pycache_prefix": "fresh-private-cache"}}


def bootstrap_guard() -> Path:
    launch_metadata()
    if (
        Path(sys.executable).resolve() != CORE.resolve()
        or sys.implementation.name != "cpython"
        or sys.version_info[:2] != (3, 11)
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.dont_write_bytecode
        or sys.flags.optimize != 0
        or set(sys._xoptions) != {"pycache_prefix"}
        or sys.gettrace() is not None
        or sys.getprofile() is not None
        or Path.cwd().resolve() != ROOT
    ):
        raise ValueError("b1_fixed_fresh_isolated_core_required")
    cache = Path(sys.pycache_prefix).resolve() if sys.pycache_prefix else None
    if (
        cache is None
        or not cache.is_relative_to(ROOT / "private/tmp")
        or not cache.is_dir()
        or any(cache.iterdir())
    ):
        raise ValueError("b1_fresh_private_cache_required")
    return cache


def _safe_source(path: Path) -> bytes:
    actual = path.resolve()
    if (
        actual != path.absolute()
        or not actual.is_relative_to(ROOT)
        or not actual.is_file()
    ):
        raise ValueError("b1_worktree_source_path_refused")
    return actual.read_bytes()


def source_snapshot(inventory: dict, git: MetadataGit) -> dict:
    with git.installed():
        validate_own_inventory(ROOT, inventory)
        head = git.read(ROOT, "rev-parse", "HEAD").decode("ascii").strip()
        delta = git.read(
            ROOT, "diff", "--name-only", "-z", "--no-renames", inventory["commit"], head
        )
        paths = [row.decode("utf-8") for row in delta.split(b"\0") if row]
        if any(path.endswith(".py") or path in CONFIGS for path in paths):
            raise ValueError("b1_head_source_or_configuration_changed")
        untracked = git.read(
            ROOT, "ls-files", "--others", "--exclude-standard", "-z", "--", "*.py"
        )
        if untracked.strip(b"\0"):
            raise ValueError("b1_uncommitted_python_refused")
        configs = {
            path: git.read(ROOT, "rev-parse", inventory["commit"] + ":" + path)
            .decode()
            .strip()
            for path in CONFIGS
        }
        config_bytes = raw_sources(ROOT, configs)
    files, raw_hashes = {}, {}
    for row in inventory["static_source_guards"]:
        raw = _safe_source(ROOT / row["path"])
        if hashlib.sha256(normalized(raw)).hexdigest() != row["lf_sha256"]:
            raise ValueError("b1_worktree_source_changed")
        raw_hashes[row["path"]] = hashlib.sha256(raw).hexdigest()
        files[str((ROOT / row["path"]).resolve())] = raw_hashes[row["path"]]
    for path, expected in config_bytes.items():
        raw = _safe_source(ROOT / path)
        if normalized(raw) != normalized(expected):
            raise ValueError("b1_worktree_configuration_changed")
        files[str((ROOT / path).resolve())] = hashlib.sha256(raw).hexdigest()
    return {
        "observed_HEAD": head,
        "files": files,
        "raw_sha256": raw_hashes,
        "git_configuration": git.configuration(),
    }


def _walk_files(path: Path) -> list[Path]:
    if path.is_symlink():
        raise ValueError("b1_dependency_symlink_refused")
    if path.is_file():
        return [path.resolve()]
    if not path.is_dir():
        raise ValueError("b1_dependency_path_missing")
    result = []
    for current, directories, filenames in os.walk(path, followlinks=False):
        directories[:] = [
            name for name in directories if name not in ("__pycache__", "site-packages")
        ]
        parent = Path(current)
        if parent.is_symlink() or any(
            (parent / name).is_symlink() for name in directories
        ):
            raise ValueError("b1_dependency_symlink_refused")
        for name in filenames:
            file = parent / name
            if file.is_symlink():
                raise ValueError("b1_dependency_symlink_refused")
            if file.suffix != ".pyc":
                result.append(file.resolve())
    return result


def _locked_versions() -> dict[str, str]:
    result = {}
    for name in ("requirements-core.lock", "requirements-test.lock"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if "==" in line and not line.startswith("#"):
                package, version = line.split("==", 1)
                result[package.lower().replace("_", "-")] = version.strip()
    return result


def runtime_snapshot() -> dict:
    site = CORE.parent.parent / "Lib/site-packages"
    base = Path(sys.base_prefix).resolve()
    roots = [
        base / "Lib",
        base / "DLLs",
        CORE.resolve(),
        Path(sys._base_executable).resolve(),
    ]
    roots.extend(path for path in base.glob("python*.dll") if path.is_file())
    roots.extend(path for path in base.glob("python*.zip") if path.is_file())
    versions, locked = {}, _locked_versions()
    for name, modules in PACKAGES.items():
        dist = importlib.metadata.distribution(name)
        version = dist.version
        if locked.get(name.lower().replace("_", "-")) != version:
            raise ValueError("b1_dependency_version_not_locked")
        versions[name] = version
        metadata = Path(dist._path).resolve()
        if not metadata.is_relative_to(site.resolve()):
            raise ValueError("b1_dependency_metadata_outside_core")
        roots.append(metadata)
        roots.extend(site / module for module in modules)
    files = {}
    for path in roots:
        for file in _walk_files(path):
            files[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
    result = {
        "python": {
            "executable": str(CORE.resolve()),
            "base_executable": str(Path(sys._base_executable).resolve()),
            "version": list(sys.version_info[:3]),
            "implementation": sys.implementation.name,
        },
        "launch": launch_metadata(),
        "versions": versions,
        "files": dict(sorted(files.items())),
        "limits": [
            "Pinned installed content, not native-code coverage or an operating-system sandbox."
        ],
    }
    result["runtime_sha256"] = digest(result)
    return result


def loaded_modules(files: dict[str, str]) -> dict[str, str]:
    result = {}
    for name, module in tuple(sys.modules.items()):
        value = getattr(module, "__file__", None)
        if value is None:
            continue
        path = str(Path(value).resolve())
        if path not in files:
            raise ValueError("b1_loaded_module_not_fingerprinted")
        result[name] = path
    return dict(sorted(result.items()))
