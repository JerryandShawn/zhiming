"""Synthetic miniature fixtures prove the evaluator never opens B before its freeze gate."""

import copy
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from mingjing_core.organize.v2.contracts import Prediction
from tools.eval import mod_organize_v2_eval as protocol
from tools.eval.mod_organize_v2_topics import (
    message_from_record,
    scope_for,
    topic_metrics,
)


def synthetic_repo(tmp_path):
    source = tmp_path / "mingjing_core/organize/v2/synthetic.py"
    source.parent.mkdir(parents=True)
    source.write_text("SYNTHETIC_VERSION = 1\n", encoding="utf-8")
    for relative in (protocol.MAPPING_PATH, *protocol.EVALUATOR_PATHS):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((protocol.ROOT / relative).read_bytes())
    return tmp_path


def test_prepare_manifest_reads_source_and_mapping_without_any_blind_fixture(tmp_path):
    root = synthetic_repo(tmp_path)
    assert not (root / protocol.BLIND_PATH).exists()
    manifest = protocol.prepare_manifest(root=root)
    assert manifest["status"] == "preblind_frozen" and manifest["fixture_sha256"] == protocol.BLIND_SHA
    assert manifest["frozen_at"].endswith("+08:00")
    protocol.validate_manifest(manifest, root=root)


@pytest.mark.parametrize("alter", ["source", "settings", "mapping", "evaluator", "status"])
def test_every_freeze_change_is_detected_before_accessing_any_blind_file(tmp_path, alter):
    root = synthetic_repo(tmp_path)
    manifest = protocol.prepare_manifest(root=root)
    if alter == "source":
        (root / "mingjing_core/organize/v2/synthetic.py").write_text("SYNTHETIC_VERSION = 2\n", encoding="utf-8")
    elif alter == "settings":
        manifest["settings"]["context_weight"] = 0
    elif alter == "mapping":
        (root / protocol.MAPPING_PATH).write_text("{}", encoding="utf-8")
    elif alter == "evaluator":
        (root / protocol.SELF_PATH).write_text("changed", encoding="utf-8")
    else:
        manifest["status"] = "not_frozen"
    with pytest.raises(protocol.BlindProtocolError):
        protocol.validate_manifest(manifest, root=root)
    assert not (root / protocol.BLIND_PATH).exists()


def test_final_call_without_freeze_never_claims_or_opens_a_blind_fixture(tmp_path):
    root = synthetic_repo(tmp_path)
    path = root / "manifest.json"
    path.write_text(
        json.dumps({"schema": protocol.SCHEMA, "status": "not_frozen"}),
        encoding="utf-8",
    )
    with pytest.raises(protocol.BlindProtocolError, match="not_frozen"):
        protocol.run_final(
            path,
            root / "output.json",
            root=root,
            expected_manifest_sha256=protocol.digest(path.read_bytes()),
        )
    assert not (root / (path.name + ".blind_claim.json")).exists()
    assert not (root / protocol.BLIND_PATH).exists()


def test_once_claim_is_sticky_even_if_an_attempt_fails_before_fixture_loading(tmp_path):
    root = synthetic_repo(tmp_path)
    path = root / "manifest.json"
    path.write_text(json.dumps(protocol.prepare_manifest(root=root)), encoding="utf-8")
    with pytest.raises(protocol.BlindProtocolError, match="evaluation_path_invalid"):
        protocol.run_final(
            path,
            root / "output.json",
            root=root,
            expected_manifest_sha256=protocol.digest(path.read_bytes()),
        )
    assert (root / (path.name + ".blind_claim.json")).exists()
    assert b"\r\n" not in (root / (path.name + ".blind_claim.json")).read_bytes()
    with pytest.raises(protocol.BlindProtocolError, match="already_claimed"):
        protocol.run_final(
            path,
            root / "output.json",
            root=root,
            expected_manifest_sha256=protocol.digest(path.read_bytes()),
        )


class SpyClassifier:
    def __init__(self, areas):
        self.areas, self.calls = iter(areas), []

    def classify(self, text, context=None):
        self.calls.append((text, context))
        area = next(self.areas)
        return Prediction(area, 0.9 if area else 0, {area: 1} if area else {}, "synthetic_test")


def record(identity, owner, text, expected, *, group="same-label-free-group"):
    return {
        "id": identity,
        "owner_id": owner,
        "subject_id": "self",
        "content": text,
        "context_group": group,
        "expected_space": expected,
    }


def test_context_uses_previous_predictions_instead_of_gold_and_isolates_owners():
    records = [
        record("one", "owner-a", "第一段无标签合成话语", "finance"),
        record("two", "owner-b", "第二个人的无标签合成话语", "finance"),
        record("three", "owner-a", "继续刚才", "finance"),
    ]
    original = copy.deepcopy(records)
    classifier = SpyClassifier(["career", "career", "career"])
    report = protocol.evaluate_records(records, classifier, {"finance": "finance", "career": "career"})
    assert [text for text, _ in classifier.calls] == [item["content"] for item in records]
    assert classifier.calls[0][1] is classifier.calls[1][1] is None
    context = classifier.calls[2][1]
    assert context.previous_area_id == "career" and context.previous_area_id != records[0]["expected_space"]
    assert context.previous_text == records[0]["content"]
    assert context.recent_texts == (records[0]["content"],)
    assert records == original
    assert report["area_assignment"]["assigned_accuracy"] == 0
    assert report["topic_ari_clear_all"] is None and report["topic_total"] == 3
    assert all(item["content"] not in json.dumps(report, ensure_ascii=False) for item in records)


def test_missing_group_cannot_silently_create_an_ambient_history_and_unknown_gold_is_not_dropped():
    classifier = SpyClassifier(["career", None])
    records = [
        record("a", "owner", "合成第一条", "career", group=None),
        record("b", "owner", "合成第二条", None, group=None),
    ]
    report = protocol.evaluate_records(records, classifier, {"career": "career"})
    assert all(context is None for _, context in classifier.calls)
    assert report["area_assignment"]["total"] == 2
    assert report["area_assignment"]["abstentions"] == 1
    assert report["area_assignment"]["assigned_accuracy"] == 1


def test_repository_path_traversal_cannot_be_used_as_an_evaluation_input(tmp_path):
    with pytest.raises(protocol.BlindProtocolError):
        protocol.file_in_repo("../outside", root=tmp_path)


def test_external_frozen_manifest_hash_is_required_before_claim_or_fixture_access(
    tmp_path,
):
    root = synthetic_repo(tmp_path)
    path = root / "manifest.json"
    path.write_text(json.dumps(protocol.prepare_manifest(root=root)), encoding="utf-8")
    for claimed in (None, "0" * 64):
        with pytest.raises(protocol.BlindProtocolError, match="manifest_hash_mismatch"):
            protocol.run_final(path, root / "output.json", root=root, expected_manifest_sha256=claimed)
    assert not (root / (path.name + ".blind_claim.json")).exists()


def test_naive_clock_is_rejected_instead_of_using_host_timezone(tmp_path):
    root = synthetic_repo(tmp_path)
    clock = SimpleNamespace(now=lambda: datetime(2026, 10, 21, 7))
    with pytest.raises(protocol.BlindProtocolError, match="clock_must_be_aware"):
        protocol.prepare_manifest(root=root, clock=clock)


def test_destination_is_checked_before_the_one_shot_claim(tmp_path):
    root = synthetic_repo(tmp_path)
    path = root / "manifest.json"
    path.write_text(json.dumps(protocol.prepare_manifest(root=root)), encoding="utf-8", newline="\n")
    for output in (
        root / "missing-parent/report.json",
        root.parent / "outside-report.json",
    ):
        with pytest.raises(protocol.BlindProtocolError, match="destination_invalid"):
            protocol.run_final(
                path,
                output,
                root=root,
                expected_manifest_sha256=protocol.digest(path.read_bytes()),
            )
    assert not (root / (path.name + ".blind_claim.json")).exists()


def test_same_context_group_in_a_different_raw_thread_does_not_share_predictions():
    records = [
        dict(record("a", "owner", "合成第一条", "career"), thread_id="thread-a"),
        dict(record("b", "owner", "合成第二条", "career"), thread_id="thread-b"),
    ]
    classifier = SpyClassifier(["career", "career"])
    protocol.evaluate_records(records, classifier, {"career": "career"})
    assert all(context is None for _, context in classifier.calls)


def test_topic_clustering_groups_raw_scopes_and_never_receives_gold_or_context_group():
    calls = []

    class GoldGuard(dict):
        def get(self, key, default=None):
            if key == "expected_topic":
                assert len(calls) == 2
            return super().get(key, default)

    records = [
        GoldGuard(
            dict(
                record("a", "owner-a", "甲", "career", group="group-a"),
                expected_topic="one",
            )
        ),
        GoldGuard(
            dict(
                record("b", "owner-a", "乙", "career", group="group-b"),
                expected_topic="one",
            )
        ),
        GoldGuard(
            dict(
                record("a", "owner-b", "丙", "career", group="group-a"),
                expected_topic="one",
            )
        ),
    ]
    predictions = {
        (scope_for(message_from_record(item)), item["id"]): Prediction("career", 0.9, {}, "synthetic")
        for item in records
    }

    def clusterer(messages, guessed, *, scope, similarity_threshold):
        calls.append((messages, guessed, scope, similarity_threshold))
        assert all(
            not hasattr(message, "expected_topic") and not hasattr(message, "context_group") for message in messages
        )
        return (
            SimpleNamespace(
                id="same-local-id",
                message_ids=tuple(message.id for message in messages),
            ),
        )

    result = topic_metrics(records, predictions, clusterer=clusterer)
    assert sorted(len(messages) for messages, *_ in calls) == [1, 2]
    assert result["topic_ari_clear_all"] == 1


def test_review_tray_topics_preserve_coverage_but_do_not_count_as_assigned():
    records = [
        dict(record("a", "owner", "甲", "career"), expected_topic="first"),
        dict(record("b", "owner", "乙", None), expected_topic="second"),
    ]
    predictions = {
        (scope_for(message_from_record(item)), item["id"]): Prediction(area, 0.9 if area else 0, {}, "synthetic")
        for item, area in zip(records, ("career", None), strict=True)
    }

    def covered(messages, guessed, **kwargs):
        return tuple(SimpleNamespace(id="topic-" + message.id, message_ids=(message.id,)) for message in messages)

    result = topic_metrics(records, predictions, clusterer=covered)
    assert result["topic_total"] == result["topic_clear_count"] == 2
    assert result["topic_assigned_count"] == 1 and result["topic_ari_clear_assigned"] is None
    with pytest.raises(ValueError, match="coverage_incomplete"):
        topic_metrics(records, predictions, clusterer=lambda *args, **kwargs: ())
