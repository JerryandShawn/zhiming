"""Verify P8's content-bound ephemeral aliases, not astronomy or host authorization."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.streaming.json_values import freeze_json, json_object

from .contracts import BasisRef, BriefingError, integer, text

TOP_KEYS = {"version", "scope", "data", "rule_hits", "sources", "document_id", "aliases", "effects", "limits"}
ROOT_KEYS = ("version", "scope", "data", "rule_hits", "sources")


@dataclass(frozen=True)
class TransitSnapshot:
    payload: Mapping[str, Any] = field(repr=False)
    basis: tuple[BasisRef, ...]


def pointer(value: Any, path: str) -> Any:
    if type(path) is not str or not path.startswith("/") or re.search(r"~(?![01])", path):
        raise BriefingError("transit_pointer_invalid")
    current = value
    for token in path[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(current):
            current = current[int(key)]
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise BriefingError("transit_pointer_missing")
    return current


def validate_transit(
    value: Mapping[str, Any], *, scope: FollowupScope, day: date, profile_revision: int
) -> TransitSnapshot:
    try:
        integer(profile_revision)
        payload = json_object(value)
        _envelope(payload, scope, day, profile_revision)
        document_id = "tool-" + fingerprint({key: payload[key] for key in ROOT_KEYS})
        if payload["document_id"] != document_id:
            raise BriefingError("transit_document_hash_mismatch")
        charts, names = _chart_aliases(payload, document_id)
        rules = _rule_aliases(payload, document_id, names)
        if payload["aliases"] != {"c": charts, "r": rules}:
            raise BriefingError("transit_alias_mismatch")
        refs = tuple(
            BasisRef(
                row["alias"],
                row.get("rule_id", row["claim_id"]),
                profile_revision,
                scope.owner_id,
                scope.subject_id,
                row["value_sha256"],
                document_id,
                row["path"],
                row["claim_id"],
            )
            for row in (*charts, *rules)
        )
        return TransitSnapshot(freeze_json(payload), refs)
    except BriefingError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, OverflowError, RecursionError):
        raise BriefingError("transit_snapshot_invalid") from None


def _envelope(payload: dict[str, Any], scope: FollowupScope, day: date, revision: int) -> None:
    if set(payload) != TOP_KEYS or payload["version"] != "p8-daily-transit-v1":
        raise BriefingError("transit_version_shape_invalid")
    identity = payload["scope"]
    if set(identity) != {"owner_user_id", "subject_id", "revision", "operation_id"}:
        raise BriefingError("transit_scope_shape_invalid")
    integer(identity["revision"])
    text(identity["operation_id"])
    if (identity["owner_user_id"], identity["subject_id"], identity["revision"]) != (
        scope.owner_id,
        scope.subject_id,
        revision,
    ):
        raise BriefingError("transit_scope_or_profile_revision_mismatch")
    data = payload["data"]
    if set(data) != {"date", "snapshot_at", "snapshot_at_utc", "time_basis", "bazi", "ziwei", "astro"}:
        raise BriefingError("transit_data_shape_invalid")
    stamp, utc_stamp = datetime.fromisoformat(data["snapshot_at"]), datetime.fromisoformat(data["snapshot_at_utc"])
    if data["date"] != day.isoformat() or stamp.date() != day or stamp.time().isoformat() != "12:00:00":
        raise BriefingError("transit_target_day_or_noon_mismatch")
    if (
        stamp.utcoffset() != timedelta(hours=8)
        or utc_stamp.utcoffset() != timedelta()
        or stamp.astimezone(UTC) != utc_stamp
    ):
        raise BriefingError("transit_snapshot_instant_mismatch")
    if payload["effects"] != {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"}:
        raise BriefingError("transit_effects_invalid")
    if any(type(payload["effects"][key]) is not int for key in ("model_calls", "writes")):
        raise BriefingError("transit_effects_invalid")
    if (
        not isinstance(payload["sources"], list)
        or len(payload["sources"]) < 3
        or not all(isinstance(item, dict) for item in payload["sources"])
    ):
        raise BriefingError("transit_sources_invalid")
    if (
        not isinstance(payload["limits"], list)
        or not payload["limits"]
        or any(type(item) is not str for item in payload["limits"])
    ):
        raise BriefingError("transit_limits_required")
    if not isinstance(payload["rule_hits"], list) or len(payload["rule_hits"]) > 4096:
        raise BriefingError("transit_rule_hits_invalid")


def _chart_aliases(payload: dict[str, Any], document_id: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    paths = set()
    for hit in payload["rule_hits"]:
        if not isinstance(hit, dict) or set(hit) != {"rule_id", "met", "school", "source", "evidence_paths", "context"}:
            raise BriefingError("transit_hit_shape_invalid")
        if hit["met"] is not True or not isinstance(hit["source"], dict) or not hit["source"]:
            raise BriefingError("transit_hit_source_required")
        text(hit["rule_id"])
        text(hit["school"])
        context, evidence = hit["context"], hit["evidence_paths"]
        if not isinstance(context, dict) or context.get("system") not in {"bazi", "ziwei", "astro"}:
            raise BriefingError("transit_hit_context_invalid")
        if not isinstance(evidence, list) or not evidence or len(set(evidence)) != len(evidence):
            raise BriefingError("transit_evidence_paths_invalid")
        if any(type(path) is not str or not path.startswith("/data/") for path in evidence):
            raise BriefingError("transit_data_pointer_required")
        paths.update(evidence)
    rows, names = [], {}
    for index, path in enumerate(sorted(paths), 1):
        digest = fingerprint(pointer(payload, path))
        name = f"c{index}"
        rows.append(
            {
                "alias": name,
                "path": path,
                "value_sha256": digest,
                "claim_id": "claim-" + fingerprint([document_id, path, digest]),
            }
        )
        names[path] = name
    return rows, names


def _rule_aliases(payload: dict[str, Any], document_id: str, names: Mapping[str, str]) -> list[dict[str, Any]]:
    rows = []
    for index, hit in enumerate(payload["rule_hits"], 1):
        path = f"/rule_hits/{index - 1}"
        digest = fingerprint(hit)
        rows.append(
            {
                "alias": f"r{index}",
                "path": path,
                "rule_id": hit["rule_id"],
                "value_sha256": digest,
                "claim_id": "claim-" + fingerprint([document_id, path, digest]),
                "evidence_aliases": [names[item] for item in hit["evidence_paths"]],
            }
        )
    return rows
