"""Synthetic v3 transcript answers run through both pure rule paths with the same evidence.

These comparisons cover rule migration, not chart computation, source selection,
database isolation, or the Agent finalize integration. Those remain mainline work.
"""

import ast
import hashlib
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mingjing_core.validation.legacy_lint import V3_SOURCE_SHA256, lint
from tests.v4.validation.legacy_support_mod import context, final_answer, original_warnings, rendered


def _answers(node: Any, inherited: dict[str, Any]) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    if isinstance(node, list):
        for child in node:
            yield from _answers(child, inherited)
    elif isinstance(node, dict):
        metadata = dict(inherited)
        for name in ("constraint", "question"):
            if isinstance(node.get(name), str):
                metadata[name] = node[name]
        intake = node.get("outputs", {}).get("intake", {}) if isinstance(node.get("outputs"), dict) else {}
        if isinstance(intake, dict) and isinstance(intake.get("plan"), dict):
            metadata["plan"] = intake["plan"]
        if "plain_summary" in node and "cited_fact_ids" in node and "cited_claim_ids" in node:
            yield node, metadata
        for child in node.values():
            yield from _answers(child, metadata)


def _cases() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    import json

    cases = []
    for path in sorted(Path("tests/fixtures").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("synthetic_only") is not True:
            continue
        for index, (answer, metadata) in enumerate(_answers(document, {})):
            cases.append((f"{path.stem}-{index}", deepcopy(answer), metadata))
    return cases


CASES = _cases()


@pytest.mark.parametrize("identity,answer,metadata", CASES, ids=[case[0] for case in CASES])
def test_synthetic_transcript_answer_has_exactly_the_v3_warnings(
    identity: str, answer: dict[str, Any], metadata: dict[str, Any]
) -> None:
    # Missing optional contract fields get the same defaults on both paths.
    final = dict(final_answer(), **answer)
    ctx = context(final)
    facts = [{"id": value, "content": "", "kind": "background"} for value in final["cited_fact_ids"]]
    facts.append({"id": "synthetic-constraint", "content": metadata.get("constraint", ""), "kind": "constraint"})
    ctx.snapshot["facts"] = facts
    ctx.calculation["claims"] = [{"claim_id": value} for value in final["cited_claim_ids"]]
    ctx.plan.update(metadata.get("plan", {}))
    ctx.run_request["message"] = metadata.get("question", "合成的本轮问题")
    findings = lint(rendered(final), ctx)
    try:
        expected = original_warnings(final, ctx)
    except ValidationError:
        assert len(findings) == 1 and findings[0].rule == "lint_schema_error", identity
    else:
        assert [finding.message for finding in findings] == expected, identity


def test_only_explicitly_synthetic_transcripts_are_used_and_corpus_is_substantial() -> None:
    assert len(CASES) >= 50
    assert len({case[0].rsplit("-", 1)[0] for case in CASES}) >= 15


def test_copied_source_identity_is_exact_and_no_v3_file_was_rewritten() -> None:
    source = Path("mingjing_core/application/consultation.py").read_text(encoding="utf-8")
    node = next(
        item for item in ast.walk(ast.parse(source)) if isinstance(item, ast.FunctionDef) and item.name == "_validate"
    )
    captured = ast.get_source_segment(source, node)
    assert captured is not None
    assert hashlib.sha256(captured.encode("utf-8")).hexdigest() == V3_SOURCE_SHA256


def test_optional_legacy_final_projection_is_a_warning_only_convenience() -> None:
    ctx = replace(context(), calculation={"claims": [], "calculation": {}}, revalidator=None)
    assert lint("我已经保存到记忆。", ctx)[0].rule == "legacy_unsupported_receipt"
    assert lint("", ctx)[0].rule == "lint_schema_error"
