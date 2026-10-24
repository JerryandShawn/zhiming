"""v29/v30 product prompt contract, no crisis-specific routing."""

import hashlib

from mingjing_core.agent.crisis import fallback_text
from mingjing_core.agent.prompts import DIRECTORY, load_prompts
from mingjing_core.application.consultation_context import crisis_policy


def test_prompt_hashes_versions_and_resolved_placeholders():
    bundle = load_prompts()
    assert bundle.manifest["files"]["system"]["version"] == "1.2.0"
    for name, row in bundle.manifest["files"].items():
        assert hashlib.sha256((DIRECTORY / row["file"]).read_bytes()).hexdigest() == row["sha256"]
        assert "{{" not in bundle.render(name)
    assert bundle.system(crisis=True) == bundle.system()
    assert bundle.render("onboarding") in bundle.system(onboarding=True)
    assert fallback_text() == "我这边暂时没法回答，稍后再试。"
    assert all(number not in bundle.system() + fallback_text() + crisis_policy() for number in ("12356", "120", "110"))


def test_five_review_rules_are_explicit_without_suppressing_natural_concern():
    system = load_prompts().system()
    for token in (
        "pending_confirmation",
        "时辰还不确定",
        "最在乎什么",
        "必须先调用 present_options",
        "知情同意",
    ):
        assert token in system
    assert "禁止关心" not in system and "禁止提及求助" not in system
