"""Synthetic offline workloads; the external driver owns timing, memory capture, and output files.

Fixture creation is outside each measured operation. No human labels, provider
outputs, delivery records, databases, or active schedulers are loaded here.
The final integer is the number of input records processed per invocation.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ProactiveNotice,
    ReceptivityState,
)
from mingjing_core.application.followups_rules import count_followups_today, decide_delivery
from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.calibration import CalibrationIdentity, CalibrationSample, calculate_calibration
from mingjing_core.validation.critic import compute_review, parse_attempts
from mingjing_core.validation.critic_contracts import ITEM_TYPES, ProgramIssue
from mingjing_core.validation.legacy_lint import LintContext, lint
from mingjing_core.validation.structural import StructuralContext, structural_check

BenchmarkCase = tuple[str, Callable[[], object], int]
ITERATIONS = 1000
NOW = datetime(2026, 10, 19, 4, tzinfo=UTC)


def _validation_workload() -> Callable[[], object]:
    clock = FrozenClock(NOW)
    text = "10月21日（周四）面试。明天10月21日再确认。我已经保存了〔f99〕。这条路径零风险。晚安。还想再聊吗？"
    lint_context = LintContext(
        snapshot={"facts": [{"id": "f1", "content": "合成偏好：简洁回答", "kind": "preference"}]},
        calculation={"claims": [], "calculation": {}},
        plan={"decision": False, "mode": "conversation", "systems": []},
        run_request={"message": "合成请求：核对面试安排"},
    )
    structural_context = StructuralContext(clock, aliases=frozenset({"f1"}), farewell=True, critic_available=False)

    def run() -> object:
        warning_count, structural_count = 0, 0
        for _ in range(ITERATIONS):
            warnings = lint(text, lint_context)
            result = structural_check(text, structural_context)
            assert result.text.strip() and all(
                item.rule not in {"lint_schema_error", "lint_internal_error"} for item in warnings
            )
            warning_count += len(warnings)
            structural_count += len(result.findings)
        return {"answers": ITERATIONS, "lint_warnings": warning_count, "structural_findings": structural_count}

    return run


def _critic_workload() -> Callable[[], object]:
    draft = "我已经记下了。"
    issue = {
        "item": "E2",
        "type": "false_receipt",
        "quote": draft,
        "rule": "合成声明没有成功回执",
        "evidence": "receipts",
        "fix_hint": "删除保存断言或提供成功回执",
        "confidence": 2,
    }
    raw = json.dumps({"issues": [issue]}, ensure_ascii=False)
    program = ProgramIssue("E2", draft, "保存声明须有对应回执", "receipts", "附未保存说明")

    def run() -> object:
        revised, evidence_only, parsed_attempts = 0, 0, 0
        for index in range(ITERATIONS):
            attempts = ("not-json-synthetic", raw) if index % 10 == 0 else (raw,)
            parsed = parse_attempts(attempts, draft=draft, evidence_ids=frozenset({"receipts"}))
            review = compute_review(
                parsed, program_issues=(program,), critic_allowed=index % 5 != 0, revisions_used=index % 2
            )
            revised += review.verdict == "revise"
            evidence_only += review.mode == "evidence_only"
            parsed_attempts += parsed.attempts
        return {
            "answers": ITERATIONS,
            "revised": revised,
            "evidence_only": evidence_only,
            "local_parse_attempts": parsed_attempts,
            "provider_calls": 0,
        }

    return run


def _calibration_workload() -> Callable[[], object]:
    samples = []
    for index in range(60):
        reference = {item: (index + item_index) % 2 == 0 for item_index, item in enumerate(ITEM_TYPES)}
        predicted = {item: value if index % 17 else not value for item, value in reference.items()}
        samples.append(CalibrationSample(f"synthetic-benchmark-{index}", reference, predicted))
    identity = CalibrationIdentity("synthetic-benchmark-only-v1")

    def run() -> object:
        # No provenance object is fabricated: synthetic labels can never enable live revisions.
        report = calculate_calibration(samples, identity=identity)
        assert report.complete and not report.provenance_verified
        assert all(report.state_for(item) == "record_only" for item in ITEM_TYPES)
        return {
            "synthetic_answers": report.sample_count,
            "binary_label_pairs": 60 * len(ITEM_TYPES),
            "rubric_items": len(report.items),
            "revision_enabled": False,
        }

    return run


def _delivery_workload() -> Callable[[], object]:
    scope = FollowupScope("synthetic-benchmark-owner", "self")
    clock, settings = FrozenClock(NOW), FollowupSettings()
    state = ReceptivityState(scope.owner_id, scope.subject_id)
    base = FollowupCandidate(
        "synthetic-followup",
        scope.owner_id,
        scope.subject_id,
        "followup",
        NOW,
        category="finance",
        text="合成财务内容，不输出到性能报告",
    )
    variants = (
        base,
        replace(base, source_revoked=True),
        replace(base, source_active=False),
        replace(base, kind="reminder", explicit_requested=True),
    )

    def run() -> object:
        allowed, blocked = 0, 0
        for index in range(ITERATIONS):
            decision = decide_delivery(
                variants[index % len(variants)], settings, state, scope=scope, clock=clock, sent_today=index % 3
            )
            allowed += decision.allowed
            blocked += not decision.allowed
        return {"decisions": ITERATIONS, "allowed": allowed, "blocked": blocked}

    return run


def _ledger_workload() -> Callable[[], object]:
    scope = FollowupScope("synthetic-benchmark-owner", "self")
    clock = FrozenClock(NOW)
    kinds = ("followup", "brief", "reminder")
    rows = tuple(
        ProactiveNotice(
            f"synthetic-notice-{index}",
            scope.owner_id,
            scope.subject_id,
            kinds[index % 3],
            NOW - timedelta(minutes=index),
        )
        for index in range(15)
    )

    def run() -> object:
        total = sum(count_followups_today(rows, scope=scope, clock=clock) for _ in range(ITERATIONS))
        assert total == ITERATIONS * 5
        return {
            "scoped_ledger_scans": ITERATIONS,
            "input_notice_rows": ITERATIONS * len(rows),
            "counted_followups": total,
        }

    return run


def cases() -> list[BenchmarkCase]:
    return [
        ("validation.lint_and_structural.1000_answers", _validation_workload(), ITERATIONS),
        ("validation.critic_parse_review.1000_answers", _critic_workload(), ITERATIONS),
        ("validation.calibration.60_answers_900_label_pairs", _calibration_workload(), 60),
        ("followups.delivery.1000_decisions", _delivery_workload(), ITERATIONS),
        ("followups.ledger.1000_scans_15000_notice_rows", _ledger_workload(), ITERATIONS * 15),
    ]
