"""Actual native consent, source withdrawal, clock boundaries and HTTP isolation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.synastry_consent import ConsentRequired, SynastryConsentService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.privacy_foundation import invalidate_foundation
from mingjing_core.timekit.clock import FrozenClock


@pytest.fixture
def consent(p2_repo):
    repo = p2_repo
    repo.create_subject("alice", "other", "合成人物")
    memory = MemoryService(repo)
    fields = {
        "gender": "男",
        "birth.solar_datetime": "1992-05-03 13:18:39",
        "birth.precision": "exact",
        "birth.location.lng": 104.07,
        "birth.location.lat": 30.67,
        "birth.location.tz": "Asia/Shanghai",
        "birth.clock_basis": "clock",
    }
    for subject in ("self", "other"):
        for field, value in fields.items():
            text = f"请保存资料{field}为{value}"
            source = memory.receive("alice", subject, text, source_id=subject + field)
            result = memory.save_fact("alice", subject, source["id"], text, "profile", field=field, value=value)
            assert result["write_status"] == "saved"
    source = memory.receive("alice", content="请合盘，他同意了", source_id="request-comparison")
    clock = FrozenClock(datetime(2026, 10, 27, 0, tzinfo=UTC))
    service = SynastryConsentService(repo, clock=clock)
    return SimpleNamespace(repo=repo, memory=memory, source=source, clock=clock, service=service)


def request(h, key="request-one"):
    return h.service.request("alice", "self", "other", "friendship", h.source["id"], key)


def grant(h):
    card = request(h)
    return h.service.confirm(
        "alice", card["id"], confirmed=True, expected_revision=card["revision"], request_id="click"
    )


def consume(h, card, **changes):
    args = dict(subject_a="self", subject_b="other", kind="friendship", operation_id="actual-step")
    args.update(changes)
    return h.service.consume("alice", card["id"], **args)


def test_native_pending_chat_is_not_consent_click_is_one_use_without_private_card_data(consent):
    h = consent
    card = request(h)
    assert card["state"] == "pending_confirmation" and card["uses_left"] == 0
    assert card == request(h)
    serialized = json.dumps(card, ensure_ascii=False)
    assert "1992" not in serialized and "104.07" not in serialized and "profile" not in serialized
    assert "只做这一次，不保存结果、不转发" in card["message"]
    with pytest.raises(ConsentRequired):
        consume(h, card)
    with pytest.raises(ConsentRequired):
        h.service.confirm("alice", card["id"], confirmed="他同意了", expected_revision=1, request_id="text")
    before = len(h.repo.list("alice", "fact"))
    card = grant(h)
    replay = h.service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id="click")
    assert replay == card
    assert card["uses_left"] == 1
    assert datetime.fromisoformat(card["expires_at"]) - h.clock.now() == timedelta(hours=24)
    result = consume(h, card)
    assert result["consent"] == "user_confirmed"
    assert [row["subject_id"] for row in result["snapshots"]] == ["self", "other"]
    assert h.service.card("alice", card["id"])["state"] == "consumed"
    with pytest.raises(ConsentRequired):
        consume(h, card)
    assert len(h.repo.list("alice", "fact")) == before
    for kind in ("chart", "artifact", "interpretive_claim", "note"):
        assert h.repo.list("alice", kind) == []


@pytest.mark.parametrize("changed", ["kind", "reverse", "expiry", "profile_a", "profile_b", "source", "fact_source"])
def test_bound_pair_kind_revision_expiry_and_withdrawal_cannot_reuse_grant(consent, changed):
    h = consent
    card = grant(h)
    arguments = {}
    if changed == "kind":
        arguments["kind"] = "romantic"
    elif changed == "reverse":
        arguments.update(subject_a="other", subject_b="self")
    elif changed == "expiry":
        h.clock.advance(timedelta(hours=24))
        assert h.service.card("alice", card["id"])["state"] == "expired"
    elif changed.startswith("profile_"):
        subject = "self" if changed == "profile_a" else "other"
        fact = h.repo.list("alice", "fact", subject=subject)[0]
        h.repo.update("alice", "fact", fact["id"], {"value": "changed"}, expected_revision=fact["revision"])
    else:
        source = h.source
        if changed == "fact_source":
            fact = h.repo.list("alice", "fact", subject="other")[0]
            source = h.memory.get_source("alice", fact["source_refs"][0]["message_id"])
        h.repo.delete("alice", "message", source["id"], expected_revision=source["revision"])
        invalidate_foundation(h.repo, "alice", [], [source["id"]])
        assert h.repo.get("alice", "synastry_consent", card["id"], include_deleted=True)["status"] == "deleted"
    with pytest.raises(CoreError):
        consume(h, card, **arguments)


def test_competing_consumers_cannot_spend_the_same_grant_twice(consent):
    h = consent
    card = grant(h)

    def attempt(ident):
        try:
            consume(h, card, operation_id=ident)
            return "used"
        except ConsentRequired:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ("step-a", "step-b"))) == ["denied", "used"]


def test_replayed_click_cannot_extend_expiry_and_unrelated_writes_do_not_self_invalidate(consent):
    h = consent
    card = grant(h)
    h.memory.receive("alice", content="普通后续消息", source_id="unrelated")
    assert h.service.card("alice", card["id"])["uses_left"] == 1
    h.clock.advance(timedelta(hours=24))
    replay = h.service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id="click")
    assert replay["state"] == "expired" and replay["expires_at"] == card["expires_at"]
    with pytest.raises(ConsentRequired):
        h.service.confirm("alice", card["id"], confirmed=True, expected_revision=2, request_id="new-click")
    with pytest.raises(ConsentRequired):
        consume(h, card)


def test_profile_changes_between_request_and_button_cannot_grant_old_card(consent):
    h = consent
    card = request(h)
    fact = h.repo.list("alice", "fact", subject="other")[0]
    h.repo.update("alice", "fact", fact["id"], {"value": "changed"}, expected_revision=fact["revision"])
    with pytest.raises(ConsentRequired):
        h.service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id="stale-button")
    row = h.repo.get("alice", "synastry_consent", card["id"])
    assert row["state"] == "pending_confirmation" and row["uses_left"] == 0


@pytest.mark.parametrize("mode", ["incognito", "assistant", "system", "missing", "approximate", "revoked_subject"])
def test_private_unconfirmed_or_unauthorized_profiles_never_create_consent(consent, mode):
    h = consent
    if mode in ("incognito", "assistant", "system"):
        changes = {
            "incognito": {"incognito": True},
            "assistant": {"role": "assistant"},
            "system": {"policy": {"origin": "system", "run_context": False}},
        }[mode]
        h.repo.update("alice", "message", h.source["id"], changes, expected_revision=h.source["revision"])
    elif mode in ("missing", "approximate"):
        field = "birth.location.tz" if mode == "missing" else "birth.precision"
        fact = next(row for row in h.repo.list("alice", "fact", subject="other") if row["field"] == field)
        if mode == "missing":
            h.repo.delete("alice", "fact", fact["id"], expected_revision=fact["revision"])
        else:
            h.repo.update("alice", "fact", fact["id"], {"value": "approximate"}, expected_revision=fact["revision"])
    else:
        # A new identity awaiting authorization is not an eligible second person.
        h.repo.create_subject("alice", "pending", "待确认人物", consent="pending")
    with pytest.raises(CoreError):
        if mode == "revoked_subject":
            h.service.request("alice", "self", "pending", "friendship", h.source["id"], "blocked")
        else:
            request(h)
    assert h.repo.list("alice", "synastry_consent") == []


def test_http_auth_native_button_revision_strict_schema_and_foreign_404(consent, monkeypatch):
    h = consent
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-token")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", '{"synthetic-bob":"bob"}')
    app = create_app(SimpleNamespace(repo=h.repo))
    client = TestClient(app)
    headers = {"X-Token": "synthetic-token"}
    url = "/api/synastry/consents"
    payload = dict(subject_b="other", kind="friendship", source_id=h.source["id"], request_id="http-request")
    assert client.post(url, json=payload).status_code == 401
    for extra in ({"consent": "user_confirmed"}, {"birth": "private synthetic value"}):
        response = client.post(url, json=payload | extra, headers=headers)
        assert response.status_code == 422 and "private synthetic value" not in response.text
    response = client.post(url, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    card = response.json()
    url += "/" + card["id"]
    assert client.get(url, headers={"X-Token": "synthetic-bob"}).status_code == 404
    click = dict(confirmed=True, expected_revision=card["revision"], request_id="http-click")
    for changes in ({"confirmed": "true"}, {"confirmed": False}, {"expected_revision": True}, {"consent": True}):
        assert client.post(url + "/confirm", json=click | changes, headers=headers).status_code in (400, 422)
    assert client.post(url + "/confirm", json=click, headers={"X-Token": "synthetic-bob"}).status_code == 404
    response = client.post(url + "/confirm", json=click, headers=headers)
    assert response.status_code == 200 and response.json()["uses_left"] == 1
    assert client.post(url + "/confirm", json=click, headers=headers).json() == response.json()
    assert client.post(url + "/consume", json={}, headers=headers).status_code == 404


def test_authenticated_conversation_list_only_native_current_unexpired_cards(consent, monkeypatch):
    h = consent
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-token")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", '{"synthetic-bob":"bob"}')
    monkeypatch.setattr("mingjing_core.application.synastry_consent.get_clock", lambda: h.clock)
    client = TestClient(create_app(SimpleNamespace(repo=h.repo)))
    card = request(h)
    headers = {"X-Token": "synthetic-token"}
    url = "/api/synastry/consents?conversation_id=default"
    assert client.get(url).status_code == 401
    assert client.get("/api/synastry/consents", headers=headers).status_code == 422
    assert client.get(url, headers={"X-Token": "synthetic-bob"}).json() == []
    assert client.get(url.replace("default", "other-conversation"), headers=headers).json() == []
    result = client.get(url, headers=headers)
    assert result.status_code == 200 and result.json() == [card]
    assert "1992" not in result.text and "104.07" not in result.text
    grant(h)
    assert client.get(url, headers=headers).json()[0]["state"] == "granted"
    h.clock.advance(timedelta(hours=24))
    assert client.get(url, headers=headers).json() == []
    card = request(h, "fresh")
    fact = h.repo.list("alice", "fact", subject="other")[0]
    h.repo.update("alice", "fact", fact["id"], {"value": "changed"}, expected_revision=fact["revision"])
    assert client.get(url, headers=headers).json() == []
