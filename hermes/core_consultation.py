"""Hermes CLI: identity/source transport only, all reasoning belongs to Core.

This command never sends a real message. `prepare-delivery` creates a validated
outbox event; a separately configured adapter is responsible for transport.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.hermes import HermesChannelAdapter, render_channel
from mingjing_core.adapters.channels.reports import CoreReportAdapter


def parser():
    result = argparse.ArgumentParser(description="调用明镜 Core，禁止渠道二次解释或猜测身份")
    result.add_argument("--base", default=os.environ.get("ZHIMING_BASE", os.path.expanduser("~/.hermes/zhiming")))
    result.add_argument("--channel", default=os.environ.get("ZHIMING_CHANNEL"))
    result.add_argument("--external-id", default=os.environ.get("ZHIMING_EXTERNAL_ID"))
    result.add_argument("--format", choices=("json", "text"), default="json")
    result.add_argument("--output", help="保存私人结果文件；不覆盖现有文件")
    commands = result.add_subparsers(dest="command", required=True)
    consult = commands.add_parser("consult", help="使用真实渠道用户消息 ID 问事")
    consult.add_argument("--message-id", required=True)
    consult.add_argument("--request-id", help="技术重试保留相同业务编号；默认使用渠道消息 ID")
    consult.add_argument("--binding-kind", choices=("user", "chat"), default="user")
    consult.add_argument("--conversation")
    consult.add_argument("--case", action="append")
    consult.add_argument("--depth", choices=("fast", "standard", "deep"), default="standard")
    report = commands.add_parser("report", help="生成报告，不实际投递，不随机抽塔罗")
    report.add_argument("--kind", required=True, choices=("daily", "weekly", "monthly", "quarterly"))
    report.add_argument("--date", required=True, help="Asia/Shanghai 报告日期 YYYY-MM-DD")
    report.add_argument("--operation-id", help="同一期报告的技术重试保留原编号")
    report.add_argument("--case", action="append")
    report.add_argument("--depth", choices=("fast", "standard", "deep"), default="standard")
    delivery = commands.add_parser("prepare-delivery", help="校验并建立 outbox，不执行网络发送")
    delivery.add_argument("--result-file", required=True)
    delivery.add_argument("--delivery-channel", required=True)
    delivery.add_argument("--target", required=True)
    return result


async def execute(args, *, service=None, hermes_db=None):
    if args.command == "consult":
        adapter = HermesChannelAdapter(args.base, service=service, hermes_db=hermes_db)
        return await adapter.consult(
            channel=args.channel, external_id=args.external_id, message_id=args.message_id,
            request_id=args.request_id, binding_kind=args.binding_kind,
            conversation_id=args.conversation, case_ids=args.case, depth=args.depth,
        )
    if args.channel not in (None, "report"):
        raise ValueError("报告与 outbox 准备必须使用 report 渠道绑定")
    adapter = CoreReportAdapter(args.base, service=service)
    if args.command == "report":
        return await adapter.prepare(
            external_id=args.external_id, kind=args.kind, day=args.date,
            operation_id=args.operation_id, case_ids=args.case, depth=args.depth,
        )
    if args.command == "prepare-delivery":
        result = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
        return await adapter.prepare_delivery(
            external_id=args.external_id, result=result,
            channel=args.delivery_channel, target=args.target,
        )
    raise ValueError("不支持的命令")


def main(argv=None):
    command = parser()
    args = command.parse_args(argv)
    if not args.external_id:
        command.error("需要 --external-id 或可信服务器预置的 ZHIMING_EXTERNAL_ID")
    if args.command == "consult" and not args.channel:
        command.error("问事需要 --channel 或可信服务器预置的 ZHIMING_CHANNEL")
    result = asyncio.run(execute(args))
    text = render_channel(result) if args.format == "text" and args.command != "prepare-delivery" else json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
        print(json.dumps({"ok": True, "output": str(target)}, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()
