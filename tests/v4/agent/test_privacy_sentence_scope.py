"""An earlier reported sentence cannot silence a later explicit privacy instruction."""

import pytest

from mingjing_core.application.privacy_mode_policy import privacy_action


@pytest.mark.parametrize(
    "message,expected",
    [
        ("朋友说，开个无痕。接下来这段别记。", "enter"),
        ("刚才只是在引用别人说的话。现在开个无痕。", "enter"),
        ("朋友说，结束无痕。现在结束无痕。", "exit"),
        ("朋友说，开个无痕。只是转述。", None),
        ("如果我说这段别记。只是一个假设。", None),
    ],
)
def test_direct_command_has_its_own_sentence_scope(message, expected):
    assert privacy_action(message) == expected
