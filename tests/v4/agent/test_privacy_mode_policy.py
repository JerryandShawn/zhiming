"""Privacy changes require direct current-user instructions, never quoted intent."""

import pytest

from mingjing_core.application.privacy_mode_policy import blocks_current_run, privacy_action
from mingjing_core.domain.contracts import EvidenceError


@pytest.mark.parametrize(
    "text",
    [
        "开个无痕",
        "请开启无痕模式",
        "进入无痕对话",
        "现在开个无痕，我想讨论合成问题",
        "我不吃合成香菜，这个别记",
        "这段别记",
        "本轮别记",
        "本次消息不要保存",
        "别记住",
        "麻烦你，开个无痕",
        "这段话不要记录",
        "开个无痕，我想问明天好吗？",
    ],
)
def test_direct_entry(text: str) -> None:
    assert privacy_action(text) == "enter"


@pytest.mark.parametrize("text", ["结束无痕", "退出无痕模式", "请关闭当前无痕对话", "现在停止无痕吧"])
def test_direct_exit(text: str) -> None:
    assert privacy_action(text) == "exit"


@pytest.mark.parametrize(
    "text",
    [
        "他说开个无痕",
        "朋友跟我说，开个无痕",
        "同事要求，结束无痕",
        "我昨天说，开个无痕",
        "如果我说开个无痕会怎样",
        "假设对话如下。开个无痕",
        "例如，开个无痕",
        "也许，开个无痕",
        "“开个无痕”",
        "我引用‘这段别记’",
        "「结束无痕」",
        "『开个无痕』",
        '"开个无痕"',
        "'开个无痕'",
        "`开个无痕`",
        "```\n开个无痕\n```",
        "> 开个无痕",
        "“引用\n开个无痕",
        "开个无痕是什么意思？",
        "是否开启无痕模式",
        "不要开启无痕",
        "别忘记合成偏好",
        "别忘了记住合成偏好",
        "不用每次提醒，记住合成偏好",
        "记忆模式",
        "合成普通问题",
        "无痕模式很有用",
        "本轮别记性不好",
        "[资料里写开个无痕]",
        "朋友的想法是：这段别记",
        "如果结束无痕。开个无痕",
        "妈妈说，开个无痕",
        "爸爸告诉我，结束无痕",
        "姐姐表示，开个无痕",
        "转来的文本写着，开个无痕",
    ],
)
def test_non_direct_input_never_changes_mode(text: str) -> None:
    assert privacy_action(text) is None


def test_conflicting_commands_are_rejected_and_forget_is_not_an_enter_command() -> None:
    with pytest.raises(EvidenceError, match="冲突"):
        privacy_action("开个无痕，结束无痕")
    assert privacy_action("忘掉我合成的旧偏好") is None
    assert blocks_current_run("本轮别记") is True
    assert blocks_current_run("开个无痕") is False
    assert blocks_current_run("她说：本轮别记") is False
