#!/usr/bin/env python3
"""知命档案 v2：init / get / merge / import
  python3 archive.py init
  python3 archive.py get [--section graph]
  python3 archive.py merge --json '{"calibration":{"timing_bias":"偏早半月"}}'
  python3 archive.py import --file zhiming-export.json
"""
import argparse, json, os, sys

PATH = os.path.expanduser("~/.hermes/zhiming/archive.json")

DIM = {"total": 0, "accurate": 0, "partial": 0, "off": 0}
TEMPLATE = {
  "schema_version": "2.0",
  "user": {}, "charts": {},
  "graph": {"persons": [], "relations": [], "events": []},
  "omen_dictionary": [],
  "dimension_stats": {d: dict(DIM) for d in
      ["爱情", "事业学业", "金钱", "友情", "家庭", "健康"]},
  "calibration": {"timing_bias": "", "notes": ""},
  "forecast_registry": [], "daily_log": [], "reports": [],
  "config": {"site_url": ""},
  "conversation_state": {"covered_months": [], "last_focus": "", "streak_days": 0}
}

from archive_store import deep_merge, read_json, transaction

def load():
    return read_json(PATH, TEMPLATE)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "get", "merge", "import"])
    ap.add_argument("--section")
    ap.add_argument("--json")
    ap.add_argument("--file")
    a = ap.parse_args()
    arc = load()
    if a.cmd in ("init", "get"):
        out = arc.get(a.section, {}) if a.section else arc
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif a.cmd == "merge":
        transaction(PATH, lambda data: deep_merge(data, json.loads(a.json)), TEMPLATE); print("merged.")
    else:  # import：兼容 zhiming-export 包裹与裸 archive
        ext = json.load(open(os.path.expanduser(a.file)))
        payload = ext.get("archive", ext) if isinstance(ext, dict) else {}
        transaction(PATH, lambda data: deep_merge(data, payload), TEMPLATE)
        print(f"imported {len(json.dumps(payload))} bytes -> archive.json")
        if ext.get("raw_notes"):
            print("注意：导出文件含 raw_notes，请让 AI 协助归纳入库。")

if __name__ == "__main__":
    main()
