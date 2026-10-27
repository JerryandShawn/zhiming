"""Strict, owner-authenticated transports for native memory proposal actions."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mingjing_core.agent.envelope import public_receipt
from mingjing_core.application.memory2_web_actions import MemoryWebActions
from mingjing_core.application.memory2_profile_web import ProfileWebService
from mingjing_core.domain.contracts import EvidenceError


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    subject_id: str = Field(default="self", min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=180, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


class Confirm(Action):
    remember_category: bool = False


class Undo(Action):
    change_type: Literal["slot", "confirmed_slot", "merge", "archive"]


class ProfileEdit(Action):
    text: str = Field(min_length=1, max_length=800)


def memory2_router(core, auth, body):
    router = APIRouter()

    async def invoke(request, ident, action, schema, *, change=False):
        owner, service = auth(request), core(request)
        try:
            values = schema.model_validate(await body(request))
        except ValidationError:
            raise EvidenceError("记忆动作字段无效，请刷新后重试") from None
        receipt = MemoryWebActions(service.repo).act(
            owner,
            values.subject_id,
            ident,
            action=action,
            revision=values.expected_revision,
            request_id=values.request_id,
            remember=getattr(values, "remember_category", False),
            change_type=values.change_type if change else None,
        )
        return public_receipt(receipt)

    @router.post("/api/memory2/proposals/{ident}/confirm")
    async def confirm(ident: str, request: Request):
        return await invoke(request, ident, "confirm", Confirm)

    @router.post("/api/memory2/proposals/{ident}/ignore")
    async def ignore(ident: str, request: Request):
        return await invoke(request, ident, "ignore", Action)

    @router.post("/api/memory2/proposals/{ident}/undo")
    async def undo_proposal(ident: str, request: Request):
        return await invoke(request, ident, "undo", Action)

    @router.post("/api/memory2/changes/{ident}/undo")
    async def undo_change(ident: str, request: Request):
        return await invoke(request, ident, "undo", Undo, change=True)

    router.include_router(profile_router(core, auth, body))
    return router


def profile_router(core, auth, body):
    router = APIRouter()

    @router.get("/api/memory2/profile/{ident}")
    async def profile_view(ident: str, request: Request, subject_id: str = "self"):
        owner, service = auth(request), core(request)
        return ProfileWebService(service.repo).view(owner, subject_id, ident)

    async def profile_action(request, ident, action, schema):
        owner, service = auth(request), core(request)
        try:
            values = schema.model_validate(await body(request))
        except ValidationError:
            raise EvidenceError("画像动作字段无效，请刷新后重试") from None
        return public_receipt(
            ProfileWebService(service.repo).act(
                owner,
                values.subject_id,
                ident,
                revision=values.expected_revision,
                request_id=values.request_id,
                action=action,
                text=getattr(values, "text", None),
            )
        )

    @router.post("/api/memory2/profile/{ident}/edit")
    async def profile_edit(ident: str, request: Request):
        return await profile_action(request, ident, "edit", ProfileEdit)

    @router.post("/api/memory2/profile/{ident}/delete")
    async def profile_delete(ident: str, request: Request):
        return await profile_action(request, ident, "delete", Action)

    return router
