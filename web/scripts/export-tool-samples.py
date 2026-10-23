"""Offline public P8 sample export. No model, HTTP, database or browser access.

The default destination is a new staging directory below web/test-results.
All projections are read-only; historical fixture consent grants no new consent.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from tool_samples.bazi import synastry_bazi, visible
from tool_samples.common import (
    ASPECTS,
    BRANCHES,
    ELEMENTS,
    FILES,
    LABELS,
    LIMITS,
    PILLARS,
    PLANETS,
    PREFIX,
    PURPOSES,
    REPOSITORY,
    SOURCE_REF,
    STEMS,
    WEB,
    chinese,
    day,
    digest,
    integer,
    need,
    number,
    pillars,
    pointer,
    ref,
    tokens,
    unique_object,
    verify,
)
from tool_samples.export_io import export_samples as write_export
from tool_samples.source_catalog import evidence
from tool_samples.summaries import synastry_summaries
from tool_samples.synastry import palace, project_synastry, synastry_astro, synastry_ziwei, verify_synastry_rules
from tool_samples.window import project_window, window_data, window_rules, window_weights

__all__ = [
    "ASPECTS",
    "BRANCHES",
    "ELEMENTS",
    "FILES",
    "LABELS",
    "LIMITS",
    "PILLARS",
    "PLANETS",
    "PREFIX",
    "PURPOSES",
    "REPOSITORY",
    "SOURCE_REF",
    "STEMS",
    "WEB",
    "chinese",
    "day",
    "digest",
    "evidence",
    "export_samples",
    "git",
    "integer",
    "need",
    "number",
    "palace",
    "pillars",
    "pointer",
    "project_synastry",
    "project_window",
    "ref",
    "synastry_astro",
    "synastry_bazi",
    "synastry_summaries",
    "synastry_ziwei",
    "tokens",
    "unique_object",
    "verify",
    "verify_synastry_rules",
    "visible",
    "window_data",
    "window_rules",
    "window_weights",
]


def git(*arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], cwd=REPOSITORY, check=True, capture_output=True).stdout


def export_samples(output: Path) -> dict:
    """Keep the reader injectable through this compatibility entry point."""
    return write_export(output, git)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="test-results/tools-projection",
        help="New staging directory inside web; no existing output is overwritten",
    )
    arguments = parser.parse_args()
    try:
        result = export_samples(WEB / arguments.output)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        raise SystemExit("Public tool sample export failed; no source values are printed.") from None
    print(json.dumps({"status": "exported", "files": len(result["entries"]), "model_calls": 0}))


if __name__ == "__main__":
    main()
