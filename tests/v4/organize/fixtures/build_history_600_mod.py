"""Rebuild the independently authored synthetic history; never imports the classifier."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

# The space/topic labels were chosen before the natural-language variants were written.
# Every topic has fifteen revisits; labels are not classifier output or keyword matches.
CASES = json.loads(
    Path(__file__).with_name("history_600_authoring.json").read_text(encoding="utf-8")
)["topics"]

AMBIGUOUS = [
    "先不说前面的事了，我今天有点说不上来的感觉。",
    "换个话题吧，忽然不知道从哪说起。",
    "前面先放下，我只是来坐一会儿。",
    "不接着刚才聊了，今天平平的。",
    "对了，换一件事，可我还没组织好语言。",
    "先暂停那个话题，我想缓一缓。",
    "今天没有具体要解决的事，就想打个招呼。",
    "另外，有点感慨，也说不清是什么。",
    "不聊刚才那件事，我先发个晚安。",
    "换个方向，今天也没有特别的事情。",
    "前面那件事先这样，我想安静一会儿。",
    "随便聊聊吧，我还没想好内容。",
    "先不接着说，我今天只是有点走神。",
    "换个话题，我刚刚想到的又忘了。",
    "还有别的想说，但现在找不到合适的话。",
    "不谈前面的了，今天就这样也行。",
    "另外，我想先停一下，不需要得出结论。",
    "今天只是路过，先问一声好。",
    "换个话题，我觉得有点复杂，但还说不清。",
    "先把刚才放下，我只是想有人听着。",
    "不继续那件事了，窗外天色慢慢暗下来。",
    "随便说一句，今天过得挺快。",
    "另起一段吧，我暂时没有明确的问题。",
    "那件事先到这儿，我还在整理感觉。",
    "换个方向，我今天有点想发呆。",
    "今天没有具体问题，只想聊两句。",
    "前面先不说了，我想慢慢把话找回来。",
    "另外，我今天也算平安度过了。",
    "先告一段落，我现在说不出想聊什么。",
    "不接着刚才的主题，我来道声晚安。",
]

REPLIES = [
    "我们先挑一个现在能落实的小问题，不急着一次解决。",
    "你这次在意的是{title}的具体安排，可以先把可核实的情况列出来。",
    "接着你刚才说的事，我会区分已经说清的事实和还需要确认的部分。",
    "关于{title}，先保留你的节奏；我们可以从最有把握的一步谈起。",
    "我听见你想把这件事讲得更具体，先不把一个片段扩大成结论。",
]


def _secondary(topic: str, variant: int) -> str | None:
    if topic == "job_search" and variant in {9, 13}:
        return "family"
    if topic == "mother_care":
        return "career" if variant == 9 else "wellbeing"
    if topic == "sleep_routine" and variant in {4, 9}:
        return "career"
    if topic == "home_purchase" and variant in {4, 9}:
        return "family"
    if topic == "emergency_fund" and variant == 9:
        return "family"
    return None


def build_history() -> list[dict[str, object]]:
    base = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    messages: list[dict[str, object]] = []
    visits: dict[str, int] = {}
    for day in range(30):
        for episode in range(10):
            clear = episode not in {3, 8}
            index = day * 8 + episode - (episode > 3) - (episode > 8)
            space, topic, title, variants = (
                CASES[index % len(CASES)]
                if clear
                else ("daily", "daily_uncertain", "尚未明确的话题", [])
            )
            visit = visits.get(topic, 0)
            visits[topic] = visit + 1
            content = (
                variants[visit] if clear else AMBIGUOUS[(day * 2 + (episode == 8)) % 30]
            )
            reply = (
                REPLIES[(day + episode) % len(REPLIES)].format(title=title)
                if clear
                else ("可以，我们先留一点空间；你想起具体要聊的内容时，再慢慢说。")
            )
            start = base + timedelta(
                days=day, hours=episode, minutes=(day * 7 + episode * 3) % 20
            )
            for role, text, delay in [("user", content, 0), ("assistant", reply, 2)]:
                messages.append(
                    {
                        "id": f"synthetic-message-{len(messages) + 1:04d}",
                        "role": role,
                        "content": text,
                        "at_ms": int(
                            (start + timedelta(minutes=delay)).timestamp() * 1000
                        ),
                        "owner_id": "synthetic-owner",
                        "subject_id": "synthetic-subject",
                        "expected_space": space,
                        "expected_topic": topic,
                        "clear_assignment": clear,
                        "expected_segment": f"synthetic-segment-{day * 10 + episode + 1:04d}",
                        "expected_secondary": _secondary(topic, visit)
                        if clear
                        else None,
                    }
                )
    return messages


if __name__ == "__main__":
    output = Path(__file__).with_name("history_600.json")
    output.write_text(
        json.dumps(build_history(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
