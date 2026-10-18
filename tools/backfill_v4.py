"""Explicit owner-scoped v4 backfill; default dry-run never writes user data."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.backfill import backfill
from mingjing_core.repositories.postgres import PostgresRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", required=True, help="显式数据库连接环境变量名称；不会自动加载 .env")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--schema", default="mingjing_core")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not os.environ.get(args.dsn_env):
        parser.error("指定数据库环境尚未配置")
    repo = PostgresRepository(os.environ[args.dsn_env], schema=args.schema, initialize=False)
    try:
        repo.verify_schema()
        print(json.dumps(backfill(MemoryService(repo), args.owner, apply=args.apply), ensure_ascii=False))
    finally:
        repo.close()


if __name__ == "__main__":
    main()
