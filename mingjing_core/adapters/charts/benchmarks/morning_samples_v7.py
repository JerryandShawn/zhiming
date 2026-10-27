"""Offline readable samples over verified synthetic results; never a scheduler."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from mingjing_core.skills.morning_content import morning_content

START = date(2026, 10, 21)
NAMES = {"bazi": "八字", "ziwei": "紫微", "astro": "西占"}
ACTIONS = (
    "如果今天有安排，挑一件最要紧的事，先写下需要准备什么。",
    "有需要沟通的事，可以先把想问的问题写成一句话；没有也不用找话题。",
    "做选择前，分开记下已知条件和还不知道的地方，先补一条可靠信息。",
    "手头若有没收尾的小事，选一件能轻松完成的；留白也可以。",
    "可以按自己的意愿给休息留一点空间，不必为这份内容另加任务。",
    "若本周有重要安排，核对一次时间地点；没有安排就按原来的节奏。",
    "回看最近一件实际发生的事：什么有帮助，什么可以下次调整。",
)


def readable_sample(result: dict, *, expected_scope: dict, target_date: str) -> dict:
    """Keep computed observations intact; editorial actions are never rule conclusions."""
    target = date.fromisoformat(target_date)
    offset = (target - START).days
    if not 0 <= offset < len(ACTIONS):
        raise ValueError("v7_sample_week_only")
    content = morning_content(
        result, expected_scope=expected_scope, target_date=target_date
    )
    if len(content["points"]) != 3:
        raise ValueError("v7_sample_requires_three_systems")
    return {
        "version": "p8-v7-readable-sample-v1",
        "content": content,
        "editorial_action": ACTIONS[offset],
        "action_origin": "calendar_rotation_not_chart_inference",
        "markdown": _render(content, offset),
    }


def _render(content: dict, offset: int) -> str:
    weekday = "一二三四五六日"[date.fromisoformat(content["date"]).weekday()]
    lines = [
        f"# 阿远 · {content['date']} 周{weekday}",
        "",
        "阿远，早安。这里是今天的一小段盘面观察，你按自己的日程安排就好。",
        "",
        "以下用北京时间今天正午12点的计算快照作参考；不是早晨已经发生的事，也不是全天走势。",
        "",
    ]
    for point in content["points"]:
        aliases = point["c_aliases"] + point["r_aliases"]
        cited = "".join(f"〔{name}〕" for name in aliases)
        lines.append(f"- {NAMES[point['system']]}：{point['observation']}{cited}")
    lines.extend(
        [
            "",
            "这些是不同体系的符号观察，不能据此断定今天会发生什么。",
            "",
            "一个可选的小建议（编辑建议，不由盘面推导）：" + ACTIONS[offset],
            "",
            "不需要回复；这份内容不要求你改变原来的安排。",
            "",
            "## 依据与口径",
            "",
            f"合成人物；原计算文档：{content['source_document_id']}。",
            "别名只属于这一天这份原结果，跨天同名不代表同一依据；正式对话须由主线登记。",
        ]
    )
    for point in content["points"]:
        source = point["source"]
        lines.append(
            f"- {NAMES[point['system']]} / {point['school']}：{source['title']}；"
            f"状态：{source['status']}。{source.get('locator', source.get('url', ''))}"
        )
    return "\n".join(lines) + "\n"


def repetition_audit(samples: list[dict]) -> dict:
    """Count unchanged source observations separately from editorial repetition."""
    if [row["content"]["date"] for row in samples] != [
        (START + timedelta(days=i)).isoformat() for i in range(7)
    ]:
        raise ValueError("v7_audit_requires_ordered_seven_days")
    observations = Counter(
        point["observation"] for row in samples for point in row["content"]["points"]
    )
    reflections = Counter(
        point["reflection"] for row in samples for point in row["content"]["points"]
    )
    return {
        "days": 7,
        "computed_points": sum(observations.values()),
        "repeated_observations": {s: n for s, n in observations.items() if n > 1},
        "original_repeated_reflections": {
            s: n for s, n in reflections.items() if n > 1
        },
        "unique_editorial_actions": len({row["editorial_action"] for row in samples}),
        "effects": {"model_calls": 0, "sends": 0, "business_writes": 0},
        "limits": "重复的真实盘面不可为求新鲜而编造；七日轮换只供样张，不接入生产。",
    }
