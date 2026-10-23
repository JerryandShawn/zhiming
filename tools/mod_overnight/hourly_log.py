"""Append the user-requested local hourly journal; performs no network or git mutation."""

import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import SystemClock  # noqa: E402


def main() -> None:
    private = ROOT / "private/mod-night"
    private.mkdir(parents=True, exist_ok=True)
    destination = ROOT / "docs/v4/daily/2026-10-19_mod.md"
    deadline = datetime(2026, 10, 19, 8, tzinfo=ZoneInfo("Asia/Taipei")).astimezone(UTC)
    clock = SystemClock()
    recorded: set[str] = set()
    while clock.now() < deadline and not (private / "hourly.stop").exists():
        now = clock.now().astimezone(ZoneInfo("Asia/Taipei"))
        key = now.strftime("%Y-%m-%d %H:00")
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        if now.minute == 0 and key not in recorded:
            status_file = private / "progress.json"
            status = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}
            phase = status.get("phase", "本地模块工作持续中")
            # Only a fixed status code and counters enter the journal, never user content or environment values.
            if phase not in {"Q1", "Q2", "Q3", "Q4", "BONUS", "FINAL"}:
                phase = "本地模块工作持续中"
            line = f"\n- {key} +08:00：小时记录，阶段 {phase}；服务器访问0、真实模型请求0、PR合并0。\n"
            with destination.open("a", encoding="utf-8", newline="\n") as output:
                output.write(line)
            recorded.add(key)
        remaining = (next_hour.astimezone(UTC) - clock.now()).total_seconds()
        time.sleep(max(1, min(20, remaining)))


if __name__ == "__main__":
    main()
