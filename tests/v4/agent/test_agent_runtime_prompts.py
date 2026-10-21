"""Pinned wording and local crisis program triggers need no provider access."""

from __future__ import annotations

import hashlib

import pytest

from mingjing_core.agent.crisis import crisis_detected, fallback_text
from mingjing_core.agent.prompts import DIRECTORY, load_prompts
from mingjing_core.application.consultation_context import crisis_policy


def test_prompt_hashes_versions_and_resolved_placeholders() -> None:
    bundle = load_prompts()
    assert bundle.manifest["files"]["system"]["version"] == "1.1.0"
    for name, row in bundle.manifest["files"].items():
        assert hashlib.sha256((DIRECTORY / row["file"]).read_bytes()).hexdigest() == row["sha256"]
        assert "{{" not in bundle.render(name)
    assert "12356" in bundle.system(crisis=True)
    assert bundle.render("onboarding") in bundle.system(onboarding=True)
    assert "120" in fallback_text() and "110" in fallback_text() and "12356" in crisis_policy()


@pytest.mark.parametrize(
    "text",
    [
        "我想死",
        "我不想活了",
        "我准备跳楼",
        "我活不下去了",
        "我想伤害自己",
        "我打算结束生命",
        "我想自杀",
        "我想轻生",
        "我准备割腕",
        "今晚我想跳楼",
        "我现在要杀人",
        "我想杀了他",
        "我想伤害别人",
        "我打算自杀",
        "我决定自杀",
    ],
)
def test_first_person_crisis_intent_triggers(text: str) -> None:
    assert crisis_detected(text)


@pytest.mark.parametrize(
    "text",
    [
        "我不想死",
        "我不想自杀",
        "我不会自杀",
        "我没有想死",
        "我想了解自杀预防",
        "我研究自杀预防",
        "我担心别人想自杀",
        "我想学习急救",
        "我想退出游戏",
        "我快笑死了",
        "我压力大但会休息",
        "我想杀死电脑里的进程",
        "新闻里有人跳楼",
        "我准备写预防轻生报告",
        "我计划周末爬山",
    ],
)
def test_non_intent_is_not_programmatically_overclassified(text: str) -> None:
    assert not crisis_detected(text)
