"""Measure real snapshot latency on 10,000 synthetic messages, without models."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from psycopg import sql
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.targets.local_db import local_dsn, verify_local_postgres


def seed(repo):
    repo.ensure_owner("p2-synthetic")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(10000):
        at = base + timedelta(seconds=index)
        data = {
            "content": "我不能上夜班" if index == 5 else f"合成性能消息{index}",
            "role": "user",
            "channel": "synthetic",
            "source_id": str(index),
            "at": at.isoformat(),
            "at_ms": int(at.timestamp() * 1000),
            "case_ids": [],
            "thread_id": "life:self",
            "conversation_id": "benchmark",
            "origin_conversation_id": "benchmark",
            "policy": {"origin": "current_user", "run_context": True},
            "search_tokens": "合成 性能 消息",
        }
        rows.append((f"p2_perf_{index:05d}", Jsonb(data), at))
    with repo.transaction("p2-synthetic") as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                sql.SQL(
                    "INSERT INTO {}(owner,kind,id,subject,data,created_at) "
                    "VALUES('p2-synthetic','message',%s,'self',%s,%s)"
                ).format(repo.table("core_entities")),
                rows,
            )
        connection.execute(sql.SQL("ANALYZE {}").format(repo.table("core_entities")))
    memory = MemoryService(repo)
    memory.save_fact("p2-synthetic", "self", "p2_perf_00005", "我不能上夜班", "constraint")
    return memory


def measure(dsn, samples=100):
    if not 20 <= samples <= 1000:
        raise ValueError("测量样本必须为 20–1000")
    canonical = local_dsn(dsn)
    verify_local_postgres(canonical)
    schema = "p2_bench_" + uuid.uuid4().hex
    repo = PostgresRepository(canonical, schema=schema)
    try:
        memory = seed(repo)
        for _ in range(10):
            memory.snapshot("p2-synthetic")
        elapsed = []
        for _ in range(samples):
            start = time.perf_counter()
            snapshot = memory.snapshot("p2-synthetic")
            elapsed.append((time.perf_counter() - start) * 1000)
        assert len(snapshot["history"]) == 30 and snapshot["history"][-1]["id"] == "p2_perf_09999"
        assert snapshot["facts"][0]["content"] == "我不能上夜班"
        assert repo.list("p2-synthetic", "message", order="desc", limit=1)[0]["id"] == "p2_perf_09999"
        with repo.transaction() as connection:
            version = connection.execute("SHOW server_version").fetchone()["server_version"]
        return {
            "messages": 10000,
            "warmup": 10,
            "samples": samples,
            "p50_ms": round(statistics.median(elapsed), 3),
            "p95_ms": round(sorted(elapsed)[math.ceil(samples * 0.95) - 1], 3),
            "max_ms": round(max(elapsed), 3),
            "latest_id": snapshot["history"][-1]["id"],
            "retained_early_constraint": True,
            "python": platform.python_version(),
            "platform": platform.system(),
            "postgres": version,
            "model_calls": 0,
            "method": "perf_counter around complete MemoryService.snapshot, real PG15, no patches",
        }
    finally:
        assert re.fullmatch(r"p2_bench_[a-f0-9]{32}", schema)
        with repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        repo.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure(os.environ.get("CORE_TEST_DSN", ""), args.samples)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if report["p95_ms"] >= 150:
        raise SystemExit("snapshot p95 未达到 150ms 目标")


if __name__ == "__main__":
    main()
