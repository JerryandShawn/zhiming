"""Independent-label benchmark; never prints synthetic or private conversation text."""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import fields
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.organize.contracts import Message  # noqa: E402
from mingjing_core.organize.engine import OrganizeEngine  # noqa: E402
from mingjing_core.organize.metrics import adjusted_rand_index  # noqa: E402


def evaluate(fixture_name: str = "history_600.json") -> dict:
    fixture = ROOT / "tests/v4/organize/fixtures" / fixture_name
    raw = fixture.read_bytes()
    records = json.loads(raw)
    allowed = {field.name for field in fields(Message)}
    messages = [Message(**{key: value for key, value in item.items() if key in allowed}) for item in records]
    engine = OrganizeEngine()
    started = perf_counter()
    proposal = engine.organize(messages)
    elapsed = perf_counter() - started
    segments = engine.segmenter.segment(messages)
    labels = {segment.id: engine.classifier.classify(segment.user_text or segment.text) for segment in segments}
    spaces = {ident: labels[part.id].space_id for part in segments for ident in part.message_ids}
    topics = {ident: topic.id for topic in proposal.topics for ident in topic.message_ids}
    truths = defaultdict(list)
    for item in records:
        truths[item["expected_segment"]].append(item)
    clear = [items for items in truths.values() if all(item["clear_assignment"] for item in items)]
    correct = sum(all(spaces[item["id"]] == item["expected_space"] for item in items) for items in clear)
    error_pairs = Counter(
        (items[0]["expected_space"], spaces[items[0]["id"]])
        for items in clear
        if not all(spaces[item["id"]] == item["expected_space"] for item in items)
    )
    clear_records = [item for item in records if item["clear_assignment"]]
    review = set(proposal.needs_review)
    ambiguous = [item for item in records if not item["clear_assignment"]]
    return {
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "messages": len(messages),
        "ground_truth_segments": len(truths),
        "predicted_segments": len(segments),
        "clear_segments": len(clear),
        "correct_clear_segments": correct,
        "space_accuracy": correct / len(clear),
        "space_accuracy_clear_messages": sum(spaces[item["id"]] == item["expected_space"] for item in clear_records)
        / len(clear_records),
        "topic_ari_all": adjusted_rand_index(
            [item["expected_topic"] for item in records], [topics[item["id"]] for item in records]
        ),
        "topic_ari_clear": adjusted_rand_index(
            [item["expected_topic"] for item in clear_records], [topics[item["id"]] for item in clear_records]
        ),
        "low_confidence_without_review": sum(
            not set(part.message_ids) <= review for part in segments if labels[part.id].needs_review
        ),
        "ambiguous_reviewed": sum(item["id"] in review for item in ambiguous),
        "ambiguous_total": len(ambiguous),
        "topic_count": len(proposal.topics),
        "elapsed_seconds": elapsed,
        "encoder_mode": proposal.encoder_mode,
        "degradation": proposal.degradation,
        "classification_errors": [
            {"expected": left, "predicted": right, "segments": count}
            for (left, right), count in sorted(error_pairs.items())
        ],
    }


if __name__ == "__main__":
    print(
        json.dumps(
            {"development": evaluate(), "holdout": evaluate("history_holdout_mod.json")}, ensure_ascii=False, indent=2
        )
    )
