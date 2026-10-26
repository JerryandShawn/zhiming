"""Authenticated web confirmation only; no consume endpoint or client consent string."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mingjing_core.application.synastry_consent import SynastryConsentService
from mingjing_core.domain.contracts import ScopeError


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=160)
    subject_a: str = Field(default="self", min_length=1, max_length=200)
    subject_b: str = Field(min_length=1, max_length=200)
    kind: Literal["romantic", "friendship", "collaboration"]
    source_id: str = Field(min_length=1, max_length=200)


class ConsentConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=160)
    confirmed: bool
    expected_revision: int = Field(ge=1)


def synastry_router(core, auth, body) -> APIRouter:
    router = APIRouter(prefix="/api/synastry/consents")

    async def validated(req, model):
        try:
            return model.model_validate(await body(req))
        except ValidationError:
            # ValidationError includes the rejected input, which may contain birth data.
            raise HTTPException(422, "合盘确认请求格式无效") from None

    def guarded(action):
        try:
            return action()
        except ScopeError:
            raise HTTPException(404, "合盘确认不存在或不在当前账户范围") from None

    @router.post("")
    async def request_consent(req: Request):
        owner, svc = auth(req), core(req)
        data = await validated(req, ConsentRequest)
        return guarded(
            lambda: SynastryConsentService(svc.repo).request(
                owner, data.subject_a, data.subject_b, data.kind, data.source_id, data.request_id
            )
        )

    @router.get("/{ident}")
    async def get_consent(ident: str, req: Request):
        owner, svc = auth(req), core(req)
        return guarded(lambda: SynastryConsentService(svc.repo).card(owner, ident))

    @router.post("/{ident}/confirm")
    async def confirm_consent(ident: str, req: Request):
        owner, svc = auth(req), core(req)
        data = await validated(req, ConsentConfirmation)
        return guarded(lambda: SynastryConsentService(svc.repo).confirm(owner, ident, **data.model_dump()))

    return router
