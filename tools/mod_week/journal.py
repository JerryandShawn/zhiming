"""Real-time Beijing hourly journal only; no Git, network or model activity."""

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import Clock, SystemClock  # noqa: E402

ZONE = ZoneInfo("Asia/Shanghai")
DEADLINE = datetime(2026, 10, 27, 22, tzinfo=ZONE)
PHASES = {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "RESERVE", "DAY", "QUEUE33", "FINAL"}


def append_hour(clock: Clock, *, root: Path = ROOT) -> bool:
    instant = clock.now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("小时记录必须提供带时区的时钟")
    local = instant.astimezone(ZONE)
    if local >= DEADLINE:
        return False
    day = max(local.date(), date(2026, 10, 21))
    target = root / "docs/v4/daily" / f"{day.isoformat()}_mod.md"
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if local.strftime("%Y-%m-%d %H:") in current:
        return False
    state_path = root / "private/mod-week/progress.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig")) if state_path.exists() else {}
    except (ValueError, OSError):
        state = {}
    phase = state.get("phase", "本地候选模块推进")
    if phase not in PHASES:
        phase = "本地候选模块推进"
    if not current:
        target.parent.mkdir(parents=True, exist_ok=True)
        current = f"# {day.isoformat()} 模块线日报（北京时间）\n\n## 实际进度\n"
        target.write_text(current, encoding="utf-8")
    with target.open("a", encoding="utf-8", newline="\n") as output:
        output.write(
            f"\n- {local:%Y-%m-%d %H:%M:%S} +08:00：小时观察，{phase}；"
            "本线仅离线新增，服务器/真实模型/飞书/合并0。此行为实际观察，不回填空档。\n"
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    clock = SystemClock()
    while clock.now().astimezone(ZONE) < DEADLINE:
        append_hour(clock)
        if args.once or (ROOT / "private/mod-week/journal.stop").exists():
            break
        time.sleep(15)


if __name__ == "__main__":
    main()
