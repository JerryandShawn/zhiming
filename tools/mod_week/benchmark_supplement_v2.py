"""Full synthetic supplement review/projection/replay/inverse observations, without persistence."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.memory2.contracts import MemoryScope, MemorySource, SourceAnchor  # noqa: E402
from mingjing_core.organize.supplement_v2 import (  # noqa: E402
    EntityRecord,
    ReviewApproval,
    SupplementSnapshot,
    TopicRecord,
    build_review_proposal,
    plan_archive_review,
    plan_review_labels,
    plan_topic_archive,
    project_plan,
    project_undo,
)
from mingjing_core.organize.v2.classifier import LocalClassifier  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

SCOPE = MemoryScope("synthetic-supplement-benchmark", "self")
AT = datetime(2026, 10, 21, tzinfo=UTC)


def entity_cycle(count: int) -> int:
    classifier, clock = LocalClassifier(), FrozenClock(AT)
    kinds = ("message", "fact", "note", "case", "draw", "legacy_archive")
    for index in range(count):
        identity, kind = f"entity-{index}", kinds[index % len(kinds)]
        text = f"合成记录{index}：工作面试简历和求职安排"
        source = MemorySource(
            identity,
            SCOPE.owner_id,
            SCOPE.subject_id,
            text,
            clock.now(),
            role="assistant" if kind == "note" else "user",
        )
        anchor = SourceAnchor(identity, 1, 0, len(text), text)
        labels = {} if index % 2 else {"topic_id": None}
        entity = EntityRecord(
            identity,
            SCOPE,
            kind,
            text,
            clock.now(),
            (anchor,),
            labels=labels,
            origin="assistant_claim" if kind == "note" else "user",
        )
        before = SupplementSnapshot(SCOPE, (entity,), sources=(source,))
        prediction = classifier.classify(text)
        assert not prediction.waiting
        proposal = build_review_proposal(before, {identity: prediction}, scope=SCOPE, operation_id=f"label-{index}")
        approval = ReviewApproval(SCOPE, proposal.fingerprint)
        plan = plan_review_labels(before, proposal, scope=SCOPE, approval=approval)
        after = project_plan(before, plan, scope=SCOPE, approval=approval)
        assert project_plan(after, plan, scope=SCOPE, approval=approval) is after
        restored = project_undo(after, plan, scope=SCOPE)
        assert restored.entities == before.entities and restored.sources == before.sources
        assert restored.operations[-1].state == "undone" and before.entities[0].labels == labels
    return count


def topic_fixture(count: int) -> SupplementSnapshot:
    texts = [f"合成话题{index}讨论学习安排" for index in range(count)]
    full = "；".join(texts)
    source = MemorySource("topic-source", SCOPE.owner_id, SCOPE.subject_id, full, AT)
    topics, offset = [], 0
    for index, text in enumerate(texts):
        anchor = SourceAnchor(source.id, 1, offset, offset + len(text), text)
        topics.append(TopicRecord(f"topic-{index}", SCOPE, AT, (anchor,), title=f"合成话题{index}"))
        offset += len(text) + 1
    return SupplementSnapshot(SCOPE, topics=tuple(topics), sources=(source,))


def archive_cycle(count: int) -> int:
    before, clock = topic_fixture(count), FrozenClock(AT + timedelta(days=15))
    proposal = plan_topic_archive(before, scope=SCOPE, clock=clock, operation_id="archive-topics")
    assert len(proposal.entries) == count
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    plan = plan_archive_review(before, proposal, scope=SCOPE, approval=approval)
    assert len(plan.ops) == count
    after = project_plan(before, plan, scope=SCOPE, approval=approval)
    assert all(topic.status == "archived" for topic in after.topics)
    restored = project_undo(after, plan, scope=SCOPE)
    assert restored.topics == before.topics and restored.sources == before.sources
    return count


def hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("benchmark_output_already_exists")
    sources = tuple(sorted((ROOT / "mingjing_core/organize/supplement_v2").glob("*.py"))) + (Path(__file__).resolve(),)
    initial_hashes = hashes(sources)
    cases = [measure("supplement_100_complete_label_review_replay_undo_chains", lambda: entity_cycle(100))]
    print("label_chains_complete", flush=True)
    cases.append(measure("supplement_1000_topic_archive_review_project_undo", lambda: archive_cycle(1000)))
    print("topic_archive_chains_complete", flush=True)
    final_hashes = hashes(sources)
    if final_hashes != initial_hashes:
        raise ValueError("benchmark_source_changed_during_measurement")
    report = write_report(args.output, cases, sources, clock=SystemClock())
    report.update(
        {
            "source_stable_during_measurement": True,
            "source_sha256_before": initial_hashes,
            "workload_notes": [
                "Each of 100 entities runs its own frozen Q5 prediction, proposal, review plan, "
                "copy projection, replay and undo",
                "Missing and explicit-null label fields alternate; six entity kinds retain raw content and anchors",
                "1000 topics share one synthetic source with distinct exact quote offsets; all are 15 days old",
                "Each observed workload includes synthetic fixture construction and correctness assertions",
                "Business clocks are FrozenClock; the report clock is SystemClock rendered explicitly in Asia/Shanghai",
                "ReviewApproval is a synthetic trusted-host receipt, not authentication or a database commit",
            ],
        }
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for case in cases:
        print(
            case["name"],
            "median_seconds",
            case["median_seconds"],
            "peak_bytes",
            case["separate_tracemalloc_peak_bytes"],
        )


if __name__ == "__main__":
    main()
