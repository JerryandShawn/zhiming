"""Authenticated thread resources reuse ingress and the frozen event adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mingjing_core.application.private_retention import retire_private_thread
from mingjing_core.application.run_acceptance import run_acceptance
from mingjing_core.application.thread_history import thread_history
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.thread_queue import owner_runtime
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError

from .event_cursor import header_cursors, resolve_event_cursor
from .thread_events import event_response


class CreateThread(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(default="self", min_length=1, max_length=200)
    incognito: bool = False


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    subject_id: str = Field(default="self", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=16000)
    conversation_id: str = Field(default="shared", min_length=1, max_length=200)
    case_ids: list[str] = Field(default_factory=list, max_length=8)
    depth: Literal["standard", "deep"] = "standard"


class CloseThread(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(default="self", min_length=1, max_length=200)


def parse_input(model: Any, value: Any) -> Any:
    try:
        return model.model_validate(value)
    except (ValidationError, TypeError):
        # Validation dumps may embed a private message; never return those dumps.
        raise EvidenceError("请求格式无效或包含尚未支持的字段") from None


def ready(service: Any, owner: str, subject: str, *, private: bool = False) -> str:
    runtime = owner_runtime(service.repo.assert_scope(owner, subject)["settings"])
    if private and runtime != "v4":
        raise EvidenceError("无痕线程需要已配置的 v4 运行时")
    if runtime == "v4":
        assembly = getattr(service, "runtime_assembly", None)
        if assembly is None:
            raise EvidenceError("v4 尚未安装")
        assembly.require_agent()
    return runtime


def thread_router(core: Callable[..., Any], auth: Callable[..., str], body: Callable[..., Any]) -> APIRouter:
    router = APIRouter()
    resource_routes(router, core, auth, body)
    message_routes(router, core, auth, body)
    event_routes(router, core, auth)
    return router


def resource_routes(router: APIRouter, core: Any, auth: Any, body: Any) -> None:
    @router.post("/api/threads")
    async def create(request: Request) -> dict:
        service, owner = core(request), auth(request)
        value = parse_input(CreateThread, await body(request))
        ready(service, owner, value.subject_id, private=value.incognito)
        row = ThreadService(service.repo).create(
            owner, subject=value.subject_id, incognito=value.incognito, request_id=value.request_id
        )
        return thread_projection(row)

    @router.get("/api/threads")
    async def listing(request: Request, subject_id: str = "self") -> list[dict]:
        service, owner = core(request), auth(request)
        service.repo.assert_scope(owner, subject_id)
        return [
            thread_projection(row)
            for row in service.repo.list(owner, "thread", subject=subject_id)
            if row["status"] == "active"
        ]

    @router.get("/api/threads/{ident}/messages")
    async def history(ident: str, request: Request, subject_id: str = "self", limit: int = 80) -> dict:
        service, owner = core(request), auth(request)
        items = thread_history(service.repo, owner, ident, subject=subject_id, limit=limit)
        return {"thread_id": ident, "items": items}


def message_routes(router: APIRouter, core: Any, auth: Any, body: Any) -> None:
    @router.post("/api/threads/{ident}/messages")
    async def send(ident: str, request: Request) -> JSONResponse:
        service, owner = core(request), auth(request)
        value = parse_input(SendMessage, await body(request))
        ready(service, owner, value.subject_id, private=ident.startswith("incognito:"))
        if ident.startswith("incognito:") and value.case_ids:
            raise EvidenceError("无痕线程不能携带长期事项")
        run = ThreadIngress(service).submit(
            owner=owner,
            subject=value.subject_id,
            thread_id=ident,
            message=value.message,
            request_id=value.request_id,
            conversation_id=value.conversation_id,
            case_ids=value.case_ids,
            depth=value.depth,
        )
        return JSONResponse(
            run_projection(service.repo, owner, run), status_code=202, headers={"Cache-Control": "no-store"}
        )

    @router.post("/api/threads/{ident}/close")
    async def close(ident: str, request: Request) -> dict:
        service, owner = core(request), auth(request)
        value = parse_input(CloseThread, await body(request))
        service.repo.assert_scope(owner, value.subject_id)
        row = service.repo.get(owner, "thread", ident, include_deleted=True)
        if row["subject_id"] != value.subject_id:
            raise ScopeError("线程不属于当前人物")
        return service.repo.mutation_request(
            owner,
            "thread-close",
            value.request_id,
            {"thread_id": ident, "subject_id": value.subject_id},
            lambda: close_private(service.repo, owner, ident, value.subject_id),
        )


def event_routes(router: APIRouter, core: Any, auth: Any) -> None:
    @router.get("/api/runs/{ident}/events")
    async def events(ident: str, request: Request, after_seq: str | None = None, after: str | None = None) -> Any:
        service, owner = core(request), auth(request)
        # Declared string params preserve OpenAPI names; raw lists retain duplicates.
        cursor = resolve_event_cursor(
            header_cursors(request.headers),
            after=request.query_params.getlist("after"),
            after_seq=request.query_params.getlist("after_seq"),
        )
        return event_response(service.repo, owner, ident, request, cursor)


def close_private(repo: Any, owner: str, ident: str, subject: str) -> dict:
    retire_private_thread(repo, owner, ident, subject=subject, expired_only=False)
    return {"id": ident, "status": "closed", "deleted": True}


def thread_projection(row: dict) -> dict:
    fields = ("id", "subject_id", "mode", "incognito", "expires_at", "status")
    return {key: row[key] for key in fields if key in row}


def run_projection(repo: Any, owner: str, run: dict) -> dict:
    return run_acceptance(repo, owner, run["id"])
