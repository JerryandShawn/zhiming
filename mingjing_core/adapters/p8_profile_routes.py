"""Native authenticated discovery only; saving reuses the existing profile route."""

from fastapi import APIRouter, Query, Request

from mingjing_core.application.p8_profile_confirmation import profile_confirmation_cards


def p8_profile_router(core, auth) -> APIRouter:
    router = APIRouter()

    @router.get("/api/subjects/self/profile/requirements")
    async def requirements(req: Request, conversation_id: str = Query(min_length=1, max_length=200)):
        return profile_confirmation_cards(core(req), auth(req), conversation_id)

    return router
