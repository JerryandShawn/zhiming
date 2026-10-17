"""Validate an explicitly supplied holiday-cn file or self-hosted URL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mingjing_core.timekit.calendar_cn import HOLIDAY_DIR, validate_holidays


def update(source: str, directory: Path = HOLIDAY_DIR) -> dict:
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        if parsed.hostname in ("github.com", "raw.githubusercontent.com", "cdn.jsdelivr.net"):
            raise ValueError("请使用本地文件或自托管节假日来源")
        with urlopen(source, timeout=20) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("节假日文件过大")
    else:
        raw = Path(source).read_bytes()
    value = validate_holidays(json.loads(raw.decode("utf-8-sig")))
    path = directory / f"{value['year']}.json"
    before = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old = {item["date"]: item for item in before.get("days", [])}
    new = {item["date"]: item for item in value["days"]}
    changes = [day for day in sorted(old.keys() | new.keys()) if old.get(day) != new.get(day)]
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return {"year": value["year"], "changed_dates": changes, "days": len(new)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="本地 JSON 路径或显式自托管 URL")
    parser.add_argument("--directory", type=Path, default=HOLIDAY_DIR)
    args = parser.parse_args()
    print(json.dumps(update(args.source, args.directory), ensure_ascii=False))


if __name__ == "__main__":
    main()
