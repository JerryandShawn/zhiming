"""One tool gate serves serial calls and bounded, ordered pure-read batches."""

from __future__ import annotations

import copy
import json
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import ValidationError

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.agent_tools_parallel_reads import PURE_READS
from mingjing_core.models.port import ToolCall

from .journal import JournalStep, input_fingerprint
from .loop_codec import tool_message

if TYPE_CHECKING:
    from .loop_cycle import LoopCycle


@dataclass(frozen=True)
class PreparedTool:
    call: ToolCall = field(repr=False)
    step: JournalStep
    context: ToolContext = field(repr=False)
    repeated: bool
    ended: bool
    immediate: ToolResult | None = field(default=None, repr=False)


class ToolBatch:
    def __init__(self, cycle: LoopCycle) -> None:
        self.cycle = cycle

    def eligible(self, call: ToolCall) -> bool:
        if call.name not in PURE_READS or call.name not in self.cycle.exposed:
            return False
        try:
            if self.cycle.registry.read_only(call.name) is not True:
                return False
            encoded = json.dumps(call.arguments, ensure_ascii=False, allow_nan=False)
        except (KeyError, TypeError, ValueError):
            return False
        # An explicit reference may depend on another result. Preserve original order.
        return not any(marker in encoded for marker in ("〔", "上一步", "上一个结果", "刚才查询"))

    def prepare(self, call: ToolCall, ended: bool) -> PreparedTool:
        cycle = self.cycle
        cycle.control.poll()
        if cycle.emit:
            cycle.emit("tool_call", {"call_id": call.id, "name": call.name, "summary": "正在处理这一步"})
        failure = None
        try:
            fingerprint = cycle.registry.fingerprint(
                call.name, call.arguments, source_versions=cycle.frozen.injected_versions
            )
        except (ValidationError, ValueError, KeyError):
            fingerprint = input_fingerprint(
                "tool", call.name, {"arguments": call.arguments, "source_versions": cycle.frozen.injected_versions}
            )
            failure = "invalid_tool_request"
        if call.name not in cycle.exposed:
            failure = "tool_unavailable"
        cycle.repeats[fingerprint] = cycle.repeats.get(fingerprint, 0) + 1
        repeated = cycle.repeats[fingerprint] >= cycle.policy.repeat_limit
        step = cycle.journal.next_or_replay(cycle.run, kind="tool", name=call.name, input_fp=fingerprint)
        code = "turn_ended" if ended else "repeated_tool" if repeated else failure
        immediate = ToolResult(ok=False, data={"code": code}, summary="本次工具未执行") if code else None
        if step.completed:
            immediate = ToolResult.model_validate(step.output)
        return PreparedTool(copy.deepcopy(call), step, cycle._context(step), repeated, ended, immediate)

    def invoke(self, prepared: PreparedTool) -> ToolResult:
        if prepared.immediate is not None:
            return prepared.immediate
        return self.cycle.registry.execute(prepared.call.name, prepared.call.arguments, prepared.context)

    def accept(self, prepared: PreparedTool, result: ToolResult) -> tuple[ToolResult, str | None]:
        cycle, call = self.cycle, prepared.call
        receipts, event = cycle.memory_receipts, None
        if receipts is not None:
            receipts.check_boundary()
        # A write may legitimately advance dependencies before its own acknowledgement.
        # Journal and registration retain the lease, cancellation and withdrawal fences.
        with cycle.registry.service.repo.transaction(cycle.run["owner"]):
            if not prepared.step.completed:
                cycle.journal.complete(prepared.step, result.model_dump())
            cycle._register(call.name, result)
            if receipts is not None:
                event = receipts.record(prepared.step, result, arguments=call.arguments, context=prepared.context)
        if receipts is not None:
            receipts.dispatch(event)
        if result.receipt:
            cycle.receipts.append(copy.deepcopy(result.receipt))
        if result.ends_turn:
            cycle.asked = copy.deepcopy(result.data.get("asked"))
        cycle.messages.append(tool_message(call.id, result, cycle.cycle, aliases=cycle.aliases))
        if cycle.emit:
            cycle.emit(
                "tool_result",
                {
                    "call_id": call.id,
                    "name": call.name,
                    "ok": result.ok,
                    "summary": "已完成" if result.ok else "这一步尚未完成",
                },
            )
        if call.name == "set_reminder" and result.data.get("privacy_confirmation"):
            from .private_confirmation import ask_privacy

            result = ask_privacy(cycle, result.data["privacy_confirmation"])
        return result, "repeated_tool" if prepared.repeated and not prepared.ended else None

    def serial(self, call: ToolCall, ended: bool = False) -> tuple[ToolResult, str | None]:
        prepared = self.prepare(call, ended)
        return self.accept(prepared, self.invoke(prepared))

    def _result(self, future: Future[ToolResult]) -> ToolResult:
        while not future.done():
            self.cycle.control.poll()
            wait((future,), timeout=0.05)
        self.cycle.control.poll()
        return future.result()

    def parallel(self, calls: list[ToolCall]) -> list[tuple[ToolResult, str | None]]:
        prepared, blocked = [], False
        for call in calls:
            item = self.prepare(call, blocked)
            prepared.append(item)
            blocked = blocked or item.repeated
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-pure-read")
        futures: list[Future[ToolResult] | None] = []
        try:
            for item in prepared:
                futures.append(None if item.immediate is not None else executor.submit(self.invoke, item))
            results = []
            for item, future in zip(prepared, futures, strict=True):
                result = self.invoke(item) if future is None else self._result(future)
                results.append(self.accept(item, result))
            return results
        finally:
            # Reads have no effects. Cancellation must not wait for a late computation.
            executor.shutdown(wait=False, cancel_futures=True)

    def execute(self, calls: list[ToolCall]) -> tuple[bool, str | None]:
        ended, stopped, index = False, None, 0
        while index < len(calls):
            end = index + 1
            if not ended and not stopped and self.eligible(calls[index]):
                while end < len(calls) and self.eligible(calls[end]):
                    end += 1
            outcomes = (
                self.parallel(calls[index:end])
                if end - index > 1
                else [self.serial(calls[index], ended or stopped is not None)]
            )
            for result, reason in outcomes:
                ended, stopped = ended or result.ends_turn, stopped or reason
            index = end
        return ended, stopped
