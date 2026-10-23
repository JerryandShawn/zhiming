"""Fixed isolated Core entrypoint; no site initialization or target preload."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def invalid_launch(root: Path, core: Path, cache: Path | None) -> bool:
    return (
        Path(sys.executable).resolve() != core.resolve()
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.dont_write_bytecode
        or sys.flags.optimize != 0
        or any(
            getattr(sys.flags, name)
            for name in (
                "debug",
                "inspect",
                "interactive",
                "verbose",
                "bytes_warning",
                "quiet",
                "dev_mode",
                "warn_default_encoding",
            )
        )
        or sys.orig_argv[1:5] != ["-I", "-S", "-B", "-X"]
        or len(sys.orig_argv) < 7
        or sys.orig_argv[5] != "pycache_prefix=" + str(sys.pycache_prefix)
        or Path(sys.orig_argv[6]).resolve() != Path(__file__).resolve()
        or set(sys._xoptions) != {"pycache_prefix"}
        or cache is None
        or not cache.is_relative_to(root / "private/tmp")
        or not cache.is_dir()
        or any(cache.iterdir())
    )


def main() -> int:
    root = Path(__file__).resolve().parents[4]
    core = root.parent / "zhiming-v4/.venv-core/Scripts/python.exe"
    cache = Path(sys.pycache_prefix).resolve() if sys.pycache_prefix else None
    if invalid_launch(root, core, cache):
        sys.stderr.write("b1_isolated_bootstrap_required\n")
        return 2
    site = core.parent.parent / "Lib/site-packages"
    if not site.is_dir():
        sys.stderr.write("b1_core_site_missing\n")
        return 2
    for key in tuple(os.environ):
        upper = key.upper()
        if any(
            word in upper
            for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "DSN", "DATABASE")
        ) or upper.startswith(
            ("KIMI_", "OPENAI_", "ANTHROPIC_", "LANGCHAIN", "LANGSMITH", "PYTEST_")
        ):
            os.environ.pop(key, None)
    os.environ.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_ADDOPTS="",
        PYDANTIC_DISABLE_PLUGINS="__all__",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
    )
    sys.path[:0] = [str(root), str(site)]
    from mingjing_core.adapters.charts.benchmarks.line_coverage_core_run import (
        main as run,
    )

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
