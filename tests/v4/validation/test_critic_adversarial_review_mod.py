"""Independent review regressions: do not touch skipped data or send stale program evidence."""

import pytest

from mingjing_core.validation.critic import compute_review
from mingjing_core.validation.critic_contracts import ProgramIssue
from mingjing_core.validation.critic_request import CriticMaterials


def test_evidence_only_does_not_even_read_a_skipped_critic_object() -> None:
    class Poison:
        @property
        def output(self) -> object:
            raise AssertionError("skipped critic result must not be read")

    result = compute_review(Poison(), critic_allowed=False)
    assert result.mode == "evidence_only"
    assert result.verdict == "pass" and result.parse_attempts == 0


@pytest.mark.parametrize("quote,evidence", [("异轮旧引句", "now"), ("当前初稿", "ghost:evidence")])
def test_program_issues_cannot_borrow_a_different_draft_or_unknown_evidence(quote: str, evidence: str) -> None:
    finding = ProgramIssue("E1", quote, "核对当前日期", evidence, "改正日期")
    with pytest.raises(ValueError, match="program findings must bind"):
        CriticMaterials("当前用户问题", "当前此刻日期", "当前初稿", program_issues=(finding,))


def test_bound_program_evidence_can_be_projected_without_a_model_call() -> None:
    finding = ProgramIssue("E2", "当前初稿已保存", "对应回执不存在", "receipts", "删除不实保存宣称")
    materials = CriticMaterials("问题", "实际日期", "当前初稿已保存", program_issues=(finding,))
    assert materials.payload()["program_issues"][0]["evidence"] == "receipts"


def test_empty_materials_do_not_publish_a_nonexistent_now_or_user_evidence_reference() -> None:
    materials = CriticMaterials("", "\n  \n", "回答")
    assert materials.evidence_ids == frozenset({"receipts"})
