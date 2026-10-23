"""Regenerable metadata-only summaries of three explicitly synthetic reflection scenarios."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.reflection_v3 import (  # noqa: E402
    ProfileDocument,
    plan_reflection_work,
    render_about_me,
    schedule_reflection,
)
from mingjing_core.memory2.contracts import MemoryFact  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.benchmark_reflection_v3 import FIXTURE, SCOPE, arguments  # noqa: E402


def summary(name: str, values: dict, document: ProfileDocument, incoming: MemoryFact) -> dict:
    decision = schedule_reflection(**values)
    result = plan_reflection_work(
        decision.intent, **values, profile=document, current_profile_revision=5, extracted_candidates=(incoming,)
    )
    view = render_about_me(
        document, snapshot=values["snapshot"], scope=SCOPE, clock=values["clock"], current_profile_revision=5
    )
    return {
        "sample": name,
        "synthetic": True,
        "schedule": decision.disposition,
        "work_status": result.status,
        "work_reason": result.reason,
        "episodes": len(result.episodes),
        "mood_and_conclusion": "not_inferred",
        "fact_candidates_not_saved": len(result.fact_candidates),
        "duplicate_candidates_not_merged": len(result.duplicates),
        "knowledge_gap_candidates_not_asked": len(result.gaps),
        "date_repair_candidates_not_written": len(result.date_repairs),
        "profile_proposals_not_applied": len(result.profile_proposals),
        "protected_profile_item_count": len(
            {item for proposal in result.profile_proposals for item in proposal.protected_item_ids}
        ),
        "archive_candidates_not_archived": len(result.archive_candidates),
        "followup_candidates_not_scheduled": len(result.followup_candidates),
        "invalidation_candidates_not_applied": len(result.invalidations),
        "about_me_sections": len(view.sections),
        "visible_about_me_items": sum(len(section.lines) for section in view.sections),
        "effects": asdict(result.effects),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists() or not destination.is_relative_to(ROOT):
        raise ValueError("synthetic_samples_need_new_local_output")
    fixture = FIXTURE.read_bytes()
    values, document, incoming = arguments(fixture)
    samples = [summary("complete_extractive_review", values, document, incoming)]
    entries = tuple(replace(row, item=replace(row.item, pinned=True, edited_by_user=True)) for row in document.entries)
    samples.append(summary("user_edited_items_protected", values, replace(document, entries=entries), incoming))
    first = values["snapshot"].sources[0]
    values["thread"] = replace(values["thread"], source_ids=(first.id,))
    old = schedule_reflection(**values).intent
    values["thread"] = replace(values["thread"], processed_sources=old.source_manifest, processed_epoch=4)
    values["snapshot"] = replace(
        values["snapshot"], sources=(replace(first, revoked=True), *values["snapshot"].sources[1:]), source_epoch=5
    )
    samples.append(summary("withdrawal_only_no_new_content", values, document, incoming))
    paths = [
        *Path("mingjing_core/application/reflection_v3").glob("*.py"),
        Path(__file__),
        FIXTURE,
        ROOT / "tools/mod_week/benchmark_reflection_v3.py",
    ]
    report = {
        "observed_at": SystemClock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "kind": "synthetic_local_metadata_only",
        "samples": samples,
        "source_sha256": {
            path.resolve().relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        },
        "limitations": [
            "No LLM reflection, real biography, queue, database write or notification",
            "All effects remain zero",
        ],
    }
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("three_synthetic_metadata_samples_written")


if __name__ == "__main__":
    main()
