"""Local synthetic composer checks. A rendered brief is never a notification or ledger write."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, time, timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.briefing_v2 import (
    BasisRef,
    BriefingError,
    BriefItem,
    BriefSourceState,
    calendar_snapshot,
    compose_briefing,
    subscription_basis,
)
from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.scheduling.brief_schedule import BriefSubscription
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest
from mingjing_core.streaming.json_values import thaw_json
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 20, 23, tzinfo=UTC)
SCOPE = FollowupScope("synthetic-owner", "self")


def setup(**changes):
    clock = FrozenClock(AT)
    subscription = BriefSubscription(SCOPE)
    ref = subscription_basis(subscription)
    state = BriefSourceState(ref.source_id, SCOPE, ref.revision, ref.value_sha256)
    values = dict(
        scope=SCOPE,
        subscription=subscription,
        settings=FollowupSettings(),
        receptivity=ReceptivityState("synthetic-owner", "self"),
        calendar=calendar_snapshot(scope=SCOPE, clock=clock),
        clock=clock,
        subscription_state=state,
    )
    values.update(changes)
    return values


def item(number=1, *, offset=timedelta(hours=1), kind="reminder", area="career", **changes):
    body = f"合成安排{number}"
    candidate = FollowupCandidate(
        f"item-{number}",
        SCOPE.owner_id,
        SCOPE.subject_id,
        kind,
        AT + offset,
        category="synthetic",
        explicit_requested=kind == "reminder",
        text=body,
    )
    candidate = replace(candidate, **changes)
    ref = BasisRef(f"m{number}", f"source-{number}", 1, SCOPE.owner_id, SCOPE.subject_id, fingerprint(body))
    state = BriefSourceState(ref.source_id, SCOPE, ref.revision, ref.value_sha256)
    request = DeliveryRequest(f"occurrence-{number}", candidate, candidate.due_at)
    return BriefItem(request, (ref,), area, (state,))


def body(result):
    return "\n".join(line.text for section in result.sections for line in section.lines)


def synthetic_transit():
    relation = {"kind": "三合", "complete": False, "transformation_established": False}
    aspect = {"from": "月亮", "to": "水星", "aspect": "六合", "angle": 60, "orb_degrees": 1.0}
    data = {
        "date": "2026-10-21",
        "snapshot_at": "2026-10-21T12:00:00+08:00",
        "snapshot_at_utc": "2026-10-21T04:00:00Z",
        "time_basis": {"primary": {"basis": "true_solar"}, "comparisons": []},
        "bazi": {"snapshot": {"day": {"stem_ten_god": "食神"}}, "interactions": {"relations": [relation]}},
        "ziwei": {},
        "astro": {"orb_limit_degrees": 2.0, "aspects": [aspect]},
    }
    entries = [
        ({"system": "bazi", "kind": "ten_god", "layer": "daily", "ten_god": "食神"}, "/data/bazi/snapshot/day"),
        (
            {"system": "bazi", "kind": "relation", "relation": "三合", "complete": False, "target_layers": ["daily"]},
            "/data/bazi/interactions/relations/0",
        ),
        (
            {
                "system": "astro",
                "kind": "aspect",
                **{key: aspect[key] for key in ("from", "to", "aspect", "orb_degrees")},
                "orb_limit": 2.0,
            },
            "/data/astro/aspects/0",
        ),
    ]
    hits = [
        {
            "rule_id": f"daily.{context['system']}.synthetic-{index}",
            "met": True,
            "school": "synthetic-convention",
            "source": {"title": "synthetic-only"},
            "evidence_paths": [path],
            "context": context,
        }
        for index, (context, path) in enumerate(entries)
    ]
    root = {
        "version": "p8-daily-transit-v1",
        "scope": {
            "owner_user_id": SCOPE.owner_id,
            "subject_id": SCOPE.subject_id,
            "revision": 1,
            "operation_id": "synthetic-op",
        },
        "data": data,
        "rule_hits": hits,
        "sources": [{"synthetic": True}] * 3,
    }
    return seal(root)


def seal(root):
    from mingjing_core.application.briefing_v2.evidence import pointer

    base = {key: root[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
    document = "tool-" + fingerprint(base)
    paths = sorted({path for hit in root["rule_hits"] for path in hit["evidence_paths"]})
    charts, rules = [], []
    for index, path in enumerate(paths, 1):
        digest = fingerprint(pointer(root, path))
        charts.append(
            dict(
                alias=f"c{index}",
                path=path,
                value_sha256=digest,
                claim_id="claim-" + fingerprint([document, path, digest]),
            )
        )
    names = {row["path"]: row["alias"] for row in charts}
    for index, hit in enumerate(root["rule_hits"], 1):
        path, digest = f"/rule_hits/{index - 1}", fingerprint(hit)
        rules.append(
            dict(
                alias=f"r{index}",
                path=path,
                rule_id=hit["rule_id"],
                value_sha256=digest,
                claim_id="claim-" + fingerprint([document, path, digest]),
                evidence_aliases=[names[path] for path in hit["evidence_paths"]],
            )
        )
    return {
        **base,
        "document_id": document,
        "aliases": {"c": charts, "r": rules},
        "effects": {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"},
        "limits": ["synthetic-only"],
    }


def transit_setup(payload=None):
    payload = payload or synthetic_transit()
    state = BriefSourceState(payload["document_id"], SCOPE, 1, payload["document_id"][5:])
    return setup(transit=payload, profile_revision=1, transit_state=state)


def test_k1_subscribed_seven_oclock_ignores_quiet_and_followup_cap():
    result = compose_briefing(**setup(sent_today=2))
    assert result.delivery.allowed and result.delivery.original_due == AT
    assert result.day.isoformat() == "2026-10-21" and result.timezone == "Asia/Shanghai"
    assert asdict(result.effects) == dict(model_calls=0, writes=0, notifications=0, scheduler_mutations=0)
    assert all(line.basis for section in result.sections for line in section.lines)
    assert result.preview == "明镜的晨报到了" and result.request_key.startswith("brief:")


@pytest.mark.parametrize(
    "change",
    [
        {"subscription_state": None},
        {"settings": FollowupSettings(proactive_enabled=False)},
        {"settings": FollowupSettings(muted_categories=frozenset({"brief"}))},
    ],
)
def test_unknown_or_disabled_brief_has_no_private_sections(change):
    result = compose_briefing(**setup(items=(item(),), **change))
    assert not result.sections and not result.delivery.allowed


def test_closed_subscription_has_no_occurrence_or_content():
    values = setup()
    values["subscription"] = replace(values["subscription"], enabled=False)
    result = compose_briefing(**values)
    assert result.delivery is None and not result.sections


@pytest.mark.parametrize(
    "field,value",
    [("active", False), ("revoked", True), ("incognito", True), ("revision", 2), ("value_sha256", "0" * 64)],
)
def test_current_subscription_source_is_rechecked(field, value):
    values = setup()
    values["subscription_state"] = replace(values["subscription_state"], **{field: value})
    result = compose_briefing(**values)
    assert not result.delivery.allowed and not result.sections


def test_user_selected_time_is_preserved_and_early_generation_does_not_push():
    values = setup()
    sub = replace(values["subscription"], local_time=time(9, 10))
    ref = subscription_basis(sub)
    values.update(
        subscription=sub, subscription_state=BriefSourceState(ref.source_id, SCOPE, ref.revision, ref.value_sha256)
    )
    result = compose_briefing(**values)
    assert result.delivery.disposition == "not_due" and result.sections
    assert result.delivery.original_due == AT + timedelta(hours=2, minutes=10)


def test_arrangements_keep_areas_and_unknown_route_is_not_called_daily():
    result = compose_briefing(**setup(items=(item(1, area="family"), item(2, area="finance"), item(3, area=None))))
    sections = {section.id: section for section in result.sections}
    assert sections["area_family"].title == "家庭" and sections["area_finance"].title == "财务"
    assert sections["area_unorganized"].title == "待整理" and "area_daily" not in sections
    assert not result.omissions


@pytest.mark.parametrize("field,value", [("source_active", False), ("source_revoked", True), ("active", False)])
def test_legacy_current_candidate_flags_still_block_private_item(field, value):
    result = compose_briefing(**setup(items=(item(**{field: value}),)))
    assert "合成安排" not in body(result) and result.omissions


@pytest.mark.parametrize(
    "field,value",
    [("active", False), ("revoked", True), ("incognito", True), ("revision", 2), ("value_sha256", "0" * 64)],
)
def test_item_current_source_manifest_blocks_stale_or_unavailable(field, value):
    row = item()
    row = replace(row, source_states=(replace(row.source_states[0], **{field: value}),))
    result = compose_briefing(**setup(items=(row,)))
    assert result.delivery.allowed and result.omissions and "合成安排" not in body(result)


def test_missing_item_current_state_is_not_inferred_from_a_short_alias():
    result = compose_briefing(**setup(items=(replace(item(), source_states=()),)))
    assert result.omissions[0].reason == "current_source_state_required"
    assert "合成安排" not in body(result)


def test_older_than_twelve_hour_reminder_cannot_hitchhike_on_brief():
    result = compose_briefing(**setup(items=(item(offset=-timedelta(hours=12, microseconds=1)),)))
    assert result.delivery.allowed and result.omissions[0].reason == "reminder_older_than_twelve_hours"
    assert "合成安排" not in body(result)


def test_followup_quiet_and_local_display_cap_are_not_overridden_by_brief():
    due = tuple(item(index, kind="followup", offset=timedelta()) for index in range(1, 4))
    quiet = compose_briefing(**setup(items=due))
    assert len(quiet.omissions) == 3 and "合成安排" not in body(quiet)
    ready = compose_briefing(**setup(items=due, settings=FollowupSettings(quiet_end=time(6)), sent_today=1))
    assert sum(section.id.startswith("area_") for section in ready.sections) == 1
    assert len(next(section for section in ready.sections if section.id == "area_career").lines) == 1
    assert len(ready.omissions) == 2 and all(value.reason == "daily_cap" for value in ready.omissions)


def test_duplicate_occurrence_dedupes_and_changed_occurrence_is_rejected():
    row = item()
    result = compose_briefing(**setup(items=(row, row)))
    assert body(result).count("合成安排1") == 1
    with pytest.raises(BriefingError):
        compose_briefing(**setup(items=(row, replace(row, area_id="family"))))


def test_valid_transit_is_a_noon_snapshot_with_full_scoped_claims():
    result = compose_briefing(**transit_setup())
    section = next(section for section in result.sections if section.id == "transit")
    assert all("北京时间12:00快照" in line.text for line in section.lines)
    assert "成员未齐，不能说完整成立" in body(result)
    assert all(ref.claim_id and ref.document_id and ref.path for line in section.lines for ref in line.basis)
    assert "transit_aliases_local_registration_required" in result.warnings


@pytest.mark.parametrize(
    "change", ["scope", "revision", "date", "snapshot", "doc", "alias", "claim", "nonzero_effect", "bool_effect"]
)
def test_bad_transit_never_renders_partial_private_content(change):
    payload = synthetic_transit()
    if change == "scope":
        payload["scope"]["owner_user_id"] = "other"
    elif change == "revision":
        payload["scope"]["revision"] = 2
    elif change == "date":
        payload["data"]["date"] = "2026-10-22"
    elif change == "snapshot":
        payload["data"]["snapshot_at"] = "2026-10-21T11:00:00+08:00"
    elif change == "doc":
        payload["document_id"] = "tool-" + "0" * 64
    elif change in {"alias", "claim"}:
        payload["aliases"]["c"][0]["alias" if change == "alias" else "claim_id"] = (
            "c99" if change == "alias" else "claim-" + "0" * 64
        )
    else:
        payload["effects"]["writes"] = 1 if change == "nonzero_effect" else False
    values = transit_setup(payload)
    result = compose_briefing(**values)
    assert not any(section.id == "transit" for section in result.sections) and result.warnings


def test_document_and_input_are_not_mutated_and_replay_key_is_stable():
    values = transit_setup()
    before = deepcopy(values["transit"])
    first, second = compose_briefing(**values), compose_briefing(**values)
    assert first == second and first.request_key == second.request_key and values["transit"] == before
    assert not any(word in body(first) for word in ("别错过", "打卡", "每天来看", "一定会", "保证"))


@pytest.mark.parametrize("changes", [{"revision": True}, {"active": "false"}, {"revoked": 1}, {"incognito": 0}])
def test_authorization_snapshot_types_are_strict(changes):
    with pytest.raises(BriefingError):
        replace(setup()["subscription_state"], **changes)


def test_stale_calendar_and_alias_rebinding_are_rejected_without_output():
    values = setup()
    values["clock"].advance(timedelta(minutes=16))
    with pytest.raises(BriefingError):
        compose_briefing(**values)
    one, two = item(1), item(2)
    two = replace(two, basis=(replace(two.basis[0], alias="m1"),))
    with pytest.raises(BriefingError):
        compose_briefing(**setup(items=(one, two)))


@pytest.mark.parametrize(
    "key,value",
    [
        ("days_to_next", True),
        ("days_to_next", -1),
        ("current_at", "2026-10-21T08:00:00+08:00"),
        ("next_at", "2026-10-21T06:00:00+08:00"),
        ("next_at", "2026-10-22T06:00:00"),
        ("current", ""),
    ],
)
def test_calendar_term_fields_match_aware_observation_and_strict_types(key, value):
    snapshot = setup()["calendar"]
    almanac = thaw_json(snapshot.almanac)
    almanac["jieqi"][key] = value
    with pytest.raises(BriefingError):
        replace(snapshot, almanac=almanac)


@pytest.mark.parametrize("changes", [{"owner_id": "foreign-owner"}, {"subject_id": "foreign-subject"}])
def test_foreign_candidate_is_rejected_without_exposing_business_id_or_body(changes):
    row = item()
    candidate = replace(row.request.candidate, id="foreign-business-secret", text="foreign-body-secret", **changes)
    row = replace(row, request=replace(row.request, candidate=candidate))
    with pytest.raises(BriefingError) as error:
        compose_briefing(**setup(items=(row,)))
    assert error.value.reason_code == "brief_candidate_scope_mismatch"
    assert all(value not in str(error.value) for value in (candidate.id, candidate.text, *changes.values()))
