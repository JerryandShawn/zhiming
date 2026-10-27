"""An outer legacy view never changes canonical envelopes or re-creates event bodies."""

from __future__ import annotations

from typing import Any

from mingjing_core.agent.events import validate_event
from mingjing_core.application.read_result import read_result
from mingjing_core.application.run_event_read import ERRORS, RunEventReader
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.event_retention_metadata import is_closed

IDENTITY = frozenset({"v", "run_id", "seq", "ts"})


class LegacyStreamProjection:
    def __init__(self, repo: Any, owner: str, ident: str) -> None:
        self.repo, self.owner, self.ident = repo, owner, ident
        self.reader = RunEventReader(repo, owner, ident)

    def project(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        kind = event["type"]
        data = validate_event(kind, event["data"])
        if data["run_id"] != self.ident:
            raise EvidenceError("兼容事件不属于当前运行")
        with self.repo.transaction(self.owner):
            run = self.reader.authority()
            if is_closed(run):
                return []
            if kind == "final":
                return self._final(run, data)
            if kind == "error":
                return self._error(run, data)
            if run["status"] in {"revoked", "cancelled"}:
                return []
            if kind == "started":
                return self._started(run, data)
            if kind in {"ask_user", "present_options"}:
                field = "asked" if kind == "ask_user" else "options"
                body = {
                    key: value for key, value in data.items() if key not in IDENTITY
                }
                if run["status"] != "succeeded":
                    return []
                if (run["result"] or {}).get(field) != body:
                    raise EvidenceError("兼容卡片与当前已提交结果不符")
                return [self._flat(kind, data, body)]
            return self._progress(kind, data)

    def _started(
        self, run: dict[str, Any], data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        request = run["request"]
        sources = request.get("source_message_ids", [request.get("source_message_id")])
        if (
            data["thread_id"] != run["thread_id"]
            or data["message_id"] not in sources
            or data["incognito"] is not request.get("incognito", False)
        ):
            raise EvidenceError("兼容开始事件与真实消息线程不符")
        return [
            self._flat(
                "started",
                data,
                dict(
                    turn_id=run["operation_id"],
                    thread_id=data["thread_id"],
                    message_id=data["message_id"],
                    reading_id=request.get("reading_id"),
                    draw_id=request.get("draw_id"),
                ),
            ),
            self._flat(
                "context",
                data,
                {
                    "meta": {
                        "core_run": self.ident,
                        "case_ids": request.get("case_ids", []),
                    }
                },
            ),
        ]

    def _final(self, run: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
        if run["status"] != "succeeded":
            return []
        if (
            run["result"] != data["envelope"]
            or run["result"].get("message_id") != data["message_id"]
        ):
            raise EvidenceError("兼容最终事件与当前已提交信封不符")
        return [
            self._flat(
                "result",
                data,
                dict(
                    result=read_result(run["result"]),
                    message_id=data["message_id"],
                    reading_id=run["request"].get("reading_id"),
                    draw_id=run["request"].get("draw_id"),
                ),
            )
        ]

    def _error(self, run: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
        if run["status"] not in ERRORS:
            return []
        proof = run["usage"].get("event_terminal_error", {})
        expected = {
            "attempts": run["attempts"],
            "epoch": run["retry_epoch"],
            "status": run["status"],
            "seq": data["seq"],
        }
        if any(proof.get(key) != value for key, value in expected.items()):
            return []
        code, message, retryable = ERRORS[run["status"]]
        if (data["code"], data["message"], data["retryable"]) != (
            code,
            message,
            retryable,
        ):
            raise EvidenceError("兼容停止事件与当前终态不符")
        return [
            self._flat(
                "error",
                data,
                {"code": code, "message": message, "retryable": retryable},
            )
        ]

    def _progress(self, kind: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        if kind == "status":
            return [
                self._flat(
                    "status", data, {"stage": data["phase"], "text": data["text"]}
                )
            ]
        if kind in {"tool_call", "tool_result"}:
            # Generic command receipts must not become unversioned memory display cards.
            return [
                self._flat("status", data, {"stage": "tool", "text": data["summary"]})
            ]
        if kind == "review":
            return [
                self._flat(
                    "status", data, {"stage": "reviewing", "text": "正在复核本轮回答"}
                )
            ]
        if kind in {"text_delta", "text_reset", "memory_receipt"}:
            body = {key: value for key, value in data.items() if key not in IDENTITY}
            return [self._flat(kind, data, body)]
        raise EvidenceError("尚未定义此公开事件的兼容投影")

    def _flat(
        self, kind: str, data: dict[str, Any], body: dict[str, Any]
    ) -> dict[str, Any]:
        return dict(body, type=kind, run_id=self.ident, seq=data["seq"])
