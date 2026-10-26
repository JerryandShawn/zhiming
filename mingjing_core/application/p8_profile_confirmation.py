"""A read-only web action from actual completed missing-input tool steps."""

from __future__ import annotations

from psycopg import sql

from mingjing_core.application.charts_natal import P8InputsRequired, natal_request
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.synastry_consent import confirmed_snapshot
from mingjing_core.domain.contracts import CoreError
from mingjing_core.timekit.clock import get_clock

FIELD_LABELS = {
    "gender": "排盘所用性别",
    "birth.solar_datetime": "阳历出生日期与当地时刻",
    "birth.location.lng": "出生地经度",
    "birth.location.lat": "出生地纬度",
    "birth.location.tz": "出生地的 IANA 时区",
    "birth.clock_basis": "出生记录的时间依据",
    "birth.precision": "出生时刻精度",
    "birth.time_uncertainty_minutes": "出生时刻误差范围",
}


def missing_input_result(error: P8InputsRequired) -> dict:
    return {
        "code": "MISSING_INPUT",
        "required_fields": [field for field in dict.fromkeys(error.fields) if field in FIELD_LABELS],
        "next_action": "profile_confirmation",
    }


def _card(service, owner: str, row: dict, conversation: str) -> dict | None:
    try:
        source = service.memory.get_source(owner, row["request"]["source_message_id"], for_context=True)
        if (
            source["status"] != "active"
            or source.get("subject_id") != "self"
            or source.get("role") != "user"
            or source.get("channel") != "web"
            or source.get("conversation_id") != conversation
            or source.get("content") != row["request"].get("message")
            or service.repo.is_revoked(owner, "message", source["id"])
            or row["state_version"].get("message:" + source["id"], source["revision"]) != source["revision"]
        ):
            return None
        snapshot = confirmed_snapshot(AgentToolsService(service.repo), owner, "self")
        # An explicit uncertain-time profile keeps the approved legacy path.
        profile = snapshot["profile"]
        if profile.get("birth.time_unknown") is True or profile.get("birth.precision") in {
            "approximate",
            "interval",
            "unknown",
        }:
            return None
        try:
            natal_request(
                snapshot,
                owner=owner,
                subject="self",
                operation_id="profile-card",
                as_of=get_clock().now().date().isoformat(),
            )
        except P8InputsRequired as error:
            fields = missing_input_result(error)["required_fields"]
            if fields:
                return {
                    "id": f"{row['id']}:{row['epoch']}:{row['seq']}",
                    "action": "open_profile",
                    "required_fields": fields,
                    "labels": [FIELD_LABELS[field] for field in fields],
                    "message": "准确排盘还需要核对这些资料。请逐项填写并明确授权保存；本次尚未计算。",
                }
    except (CoreError, KeyError):
        return None
    return None


def profile_confirmation_cards(service, owner: str, conversation: str) -> list[dict]:
    with service.repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT r.id,r.request,r.state_version,s.epoch,s.seq FROM {} r JOIN {} s ON s.owner=r.owner AND s.run_id=r.id "
                "WHERE r.owner=%s AND r.subject='self' AND r.runtime='v4' AND r.kind IN ('turn','reading') "
                "AND r.status<>'cancelled' AND r.cancel_requested_at IS NULL "
                "AND r.thread_id NOT LIKE 'incognito:%%' AND s.epoch=r.retry_epoch "
                "AND s.kind='tool' AND s.name IN ('chart_compute','daily_transit','window_search') "
                "AND s.status='completed' AND s.finished_at IS NOT NULL AND s.error_code IS NULL "
                "AND s.output->'data'->>'code'='MISSING_INPUT' "
                "AND s.output->>'ok'='false' "
                "AND s.output->'data'->>'next_action'='profile_confirmation' "
                "ORDER BY r.created_at DESC,s.seq DESC LIMIT 100"
            ).format(service.repo.table("core_runs"), service.repo.table("core_run_steps")),
            (owner,),
        ).fetchall()
        for row in rows:
            if card := _card(service, owner, row, conversation):
                return [card]
    return []
