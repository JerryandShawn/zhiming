"""Storage refusal is separate from reminders and quoted or negated instructions."""

import re

from mingjing_core.memory.policy import BENIGN_REMINDERS, mask_quoted

NEGATED_REFUSAL = re.compile(
    r"(?:没有说|没说|不是说|并非|不是|没有要求|没要求|不代表)"
    r"[^，,。；;！？!?\n]{0,8}?(?:不要|不用|不让|别|不准|不)"
    r"[^，,。；;！？!?\n]{0,8}?(?:保存|存储|记录|记住|归档|留存|记下|存|记(?!性|忆))"
)
REMINDER_REFUSAL = re.compile(r"(?:别|不要|不用|无需)(?:再|每次|一直)?(?:提醒|重复提醒)(?:我|本人)?")
STORAGE_REFUSAL = re.compile(
    r"(?:不要|不用|不许|不准|禁止|不允许|别|不想|不愿|不需要|请勿|勿|无需|不得|不能)"
    r"[^，,。；;！？!?\n]{0,20}(?:保存|存储|记录|记住|留存|留下|归档|记下|存(?:成|为|入|进|下)?(?!在|款|钱|货)|"
    r"加入.{0,5}记忆|放(?:进|入).{0,5}(?:档案|记忆)|写(?:进|入).{0,5}(?:档案|记忆))"
    r"|(?:不保存|不存储|不记录|不留存|不存(?!在|款|钱|货)|不入.{0,4}(?:档案|记忆)|不进.{0,4}(?:档案|记忆))"
    r"|(?:别|不要)记(?:住|下)?(?!性|忆)"
    r"|(?:这段|这条|这件事|本次|此事).{0,8}(?:别存|不存|不记|不要存)"
    r"|(?:这次|这段|本次|本轮).{0,6}不做.{0,5}记忆"
)


def has_storage_optout(text: str) -> bool:
    if not isinstance(text, str):
        raise ValueError("memory_text_invalid")
    plain = re.sub(r"‘[^’\n]*’", " ", mask_quoted(text))
    plain = re.sub(r"但是|不过|可是|然而|但|实际上", "，", plain)
    plain = NEGATED_REFUSAL.sub(" ", plain)
    plain = BENIGN_REMINDERS.sub(" ", plain)
    plain = REMINDER_REFUSAL.sub(" ", plain)
    return STORAGE_REFUSAL.search(plain) is not None
