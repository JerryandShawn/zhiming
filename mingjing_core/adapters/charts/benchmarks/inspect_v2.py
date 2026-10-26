"""Read already-downloaded local caches and publish only exclusion/count metadata."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .loaders_v2 import load_corpus_v2


def inspect_source(root: Path, source: str) -> dict[str, Any]:
    paths = (
        [root / "data/data.json"]
        if source == "mingli"
        else sorted((root / "data").glob("contest8_*.json"))
    )
    if source not in ("mingli", "baziqa") or not paths:
        raise ValueError("invalid_source_or_local_corpus_missing")
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    files = [load_corpus_v2(path, source).report for path in paths]
    subset = [
        load_corpus_v2(path, source, competition_year=2025).report for path in paths
    ]
    return {
        "source": source,
        "commit": commit,
        "data_policy": "existing_local_ignored_cache_only_no_download",
        "files": files,
        "source_questions": sum(row["source_questions"] for row in files),
        "schema_valid_questions": sum(row["schema_valid_questions"] for row in files),
        "included_questions": sum(row["included_questions"] for row in files),
        "excluded_questions": sum(row["excluded_questions"] for row in files),
        "requested_2025_subset": {
            "included_questions": sum(row["included_questions"] for row in subset),
            "files": subset,
            "actual_runtime_requires_separate_mainline_authorization": True,
        },
    }


def source_report(mingli_root: Path | None, baziqa_root: Path | None) -> dict[str, Any]:
    return {
        "contract": "e2-brain23-adjudication-v2",
        "real_model_requests": 0,
        "professional_corpus_score": None,
        "new_downloads": 0,
        "source_content_redistributed": False,
        "year_policy": (
            "explicit_question_target_only_no_birth_or_contest_year_fallback"
        ),
        "automatic_decisions_are_conservative": True,
        "local_review_fingerprint_and_year_span_required": True,
        "sources": [
            inspect_source(root, source)
            for root, source in ((mingli_root, "mingli"), (baziqa_root, "baziqa"))
            if root is not None
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect existing local E2 caches; no network or model transport"
    )
    parser.add_argument("--mingli-root", type=Path)
    parser.add_argument("--baziqa-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mingli_root is None and args.baziqa_root is None:
        parser.error("at least one existing local source root is required")
    report = source_report(args.mingli_root, args.baziqa_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"real_model_requests": 0, "new_downloads": 0, "output": str(args.output)}
        )
    )


if __name__ == "__main__":
    main()
