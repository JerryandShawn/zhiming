"""v3 payload projections of program time and bidirectional life history."""

from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.now_block import render_now_block
from mingjing_core.timekit.timestamps import history_instant

SYSTEM_POLICY_VERSION = "core3-policy-p2.1"


def crisis_policy() -> str:
    path = Path(__file__).resolve().parents[2] / "config" / "crisis.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if value != {"hotline": "12356", "emergency": ["120", "110"]}:
        raise ValueError("危机联系方式配置需要经过审核")
    return (
        f"用户流露自伤、轻生或危险时，先关心并确认是否安全，提供全国心理援助热线 {value['hotline']}，"
        f"紧急危险时拨打 {value['emergency'][0]} 或 {value['emergency'][1]}；不要提供其他热线号码。"
    )


def recent_history(snapshot) -> list[dict]:
    zone = ZoneInfo(snapshot["settings"].get("timezone", "Asia/Shanghai"))
    result = []
    for message in snapshot.get("history", []):
        at = history_instant(message.get("at"))
        result.append(
            {
                "role": message.get("role"),
                "at": at.astimezone(zone).strftime("%Y-%m-%d %H:%M") if at else "时间未知",
                "channel": message.get("channel", "unknown"),
                "content": message.get("content", "")[:4000],
            }
        )
    return result


def now_context(run, snapshot) -> str:
    request = run["request"]
    previous = [
        message
        for message in snapshot.get("history", [])
        if message.get("id") != request.get("source_message_id")
        and message.get("source_id") != run["operation_id"]
        and message.get("channel") != "scheduled_report"
    ]
    last = previous[-1] if previous else None
    return render_now_block(snapshot["settings"], get_clock(), last, snapshot.get("facts", []))
