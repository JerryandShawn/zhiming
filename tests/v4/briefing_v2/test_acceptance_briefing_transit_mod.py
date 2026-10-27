"""Independent P8 document/claim binding, noon labeling and conservative condition rendering."""

import copy
import json
from dataclasses import replace
from hashlib import sha256

import pytest
from brief_acceptance_support_mod import SCOPE, compose, context, public_text

from mingjing_core.application.briefing_v2 import BriefSourceState


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def resolve(value, path):
    current = value
    for token in path[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def reissue(payload):
    """Synthetic integrity-consistent tampering is still not a host authorization proof."""
    payload["document_id"] = "tool-" + digest(
        {key: payload[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
    )
    for group in ("c", "r"):
        for row in payload["aliases"][group]:
            row["value_sha256"] = digest(resolve(payload, row["path"]))
            row["claim_id"] = "claim-" + digest([payload["document_id"], row["path"], row["value_sha256"]])


def fresh_state(payload):
    return BriefSourceState(payload["document_id"], SCOPE, 1, payload["document_id"].split("-", 1)[1])


def test_valid_noon_snapshot_keeps_original_full_basis_identity_without_claiming_global_registration():
    values = context(include_transit=True)
    original = copy.deepcopy(values["transit"])
    result = compose(values)
    references = [ref for ref in result.basis if ref.document_id == original["document_id"]]
    assert references
    rendered = public_text(result)
    assert "正午" in rendered or "12:00" in rendered
    assert "当前07:00盘面" not in rendered and "1994-03-12" not in rendered
    expected = {row["alias"]: row for group in original["aliases"].values() for row in group}
    for ref in references:
        row = expected[ref.alias]
        assert (ref.path, ref.claim_id, ref.value_sha256) == (row["path"], row["claim_id"], row["value_sha256"])
        assert (ref.owner_id, ref.subject_id, ref.revision) == (SCOPE.owner_id, SCOPE.subject_id, 1)
    assert values["transit"] == original and result.effects.writes == result.effects.model_calls == 0


MUTATIONS = (
    "owner",
    "subject",
    "revision",
    "date",
    "not_noon",
    "utc_mismatch",
    "version",
    "document_id",
    "path",
    "array_index",
    "pointer_escape",
    "value_hash",
    "claim_id",
    "undefined_c",
    "duplicate_c",
    "duplicate_r",
    "r_rule_id",
    "r_hit_path",
    "r_evidence",
    "met_false",
    "missing_current_state",
    "revoked_current_state",
    "stale_current_state",
    "incognito_current_state",
)


def corrupted(values, change):
    payload = copy.deepcopy(values["transit"])
    if change in {"owner", "subject", "revision"}:
        key, value = {
            "owner": ("owner_user_id", "other"),
            "subject": ("subject_id", "other"),
            "revision": ("revision", 2),
        }[change]
        payload["scope"][key] = value
    elif change == "date":
        payload["data"].update(
            date="2026-10-22", snapshot_at="2026-10-22T12:00:00+08:00", snapshot_at_utc="2026-10-22T04:00:00Z"
        )
    elif change == "not_noon":
        payload["data"].update(snapshot_at="2026-10-21T07:00:00+08:00", snapshot_at_utc="2026-10-20T23:00:00Z")
    elif change == "utc_mismatch":
        payload["data"]["snapshot_at_utc"] = "2026-10-21T05:00:00Z"
    elif change == "version":
        payload["version"] = "unsupported-future"
    elif change == "met_false":
        payload["rule_hits"][0]["met"] = False
    if change in {"owner", "subject", "revision", "date", "not_noon", "utc_mismatch", "version", "met_false"}:
        reissue(payload)
    c, r = payload["aliases"]["c"][0], payload["aliases"]["r"][0]
    if change == "document_id":
        payload["document_id"] = "tool-" + "f" * 64
    elif change == "path":
        c["path"] = "/data/missing"
    elif change == "array_index":
        r["path"] = "/rule_hits/00"
    elif change == "pointer_escape":
        c["path"] = "/data/~2invalid"
    elif change in {"value_hash", "claim_id"}:
        c[change.replace("value_hash", "value_sha256")] = "claim-" + "f" * 64 if change == "claim_id" else "f" * 64
    elif change == "undefined_c":
        r["evidence_aliases"] = ["c99999"]
    elif change in {"duplicate_c", "duplicate_r"}:
        group = change[-1]
        payload["aliases"][group].append(copy.deepcopy(payload["aliases"][group][0]))
    elif change == "r_rule_id":
        r["rule_id"] = "daily.bazi.another"
    elif change == "r_hit_path":
        r["path"] = "/rule_hits/1"
    elif change == "r_evidence":
        r["evidence_aliases"] = ["c1"]
    state = fresh_state(payload)
    if change == "missing_current_state":
        state = None
    elif change in {"revoked_current_state", "stale_current_state", "incognito_current_state"}:
        state = replace(
            state,
            **{
                "revoked_current_state": {"revoked": True},
                "stale_current_state": {"revision": 2},
                "incognito_current_state": {"incognito": True},
            }[change],
        )
    return payload, state


@pytest.mark.parametrize("change", MUTATIONS)
def test_invalid_or_foreign_transit_is_omitted_even_when_content_hashes_are_recomputed(change):
    values = context(include_transit=True)
    payload, state = corrupted(values, change)
    result = compose(values, transit=payload, transit_state=state)
    assert not any(ref.document_id == payload["document_id"] for ref in result.basis)
    assert result.warnings and result.sections
    assert result.effects.notifications == result.effects.scheduler_mutations == 0


def test_recomputed_document_and_claim_hashes_do_not_supply_missing_source_authority():
    values = context(include_transit=True)
    payload = copy.deepcopy(values["transit"])
    payload["sources"][0]["synthetic_note"] = "SYNTHETIC_FORGED_SOURCE"
    reissue(payload)
    result = compose(values, transit=payload, transit_state=None)
    assert not any(ref.document_id == payload["document_id"] for ref in result.basis)
    assert "SYNTHETIC_FORGED_SOURCE" not in public_text(result)


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"value_sha256": "f" * 64},
        {"source_id": "another-document"},
        {"scope": replace(SCOPE, owner_id="other")},
        {"scope": replace(SCOPE, subject_id="other")},
    ],
)
def test_current_transit_state_identity_and_hash_cannot_be_substituted(change):
    values = context(include_transit=True)
    result = compose(values, transit_state=replace(values["transit_state"], **change))
    assert not any(ref.document_id == values["transit"]["document_id"] for ref in result.basis)
    assert result.warnings and result.sections


def test_incomplete_relation_and_symbolic_conditions_are_not_rendered_as_achieved_events():
    result = compose(context(include_transit=True))
    text = public_text(result)
    assert not any(phrase in text for phrase in ("三合全部成立", "三合已经形成", "合化成功", "保证发财", "一定生病"))
    for section in result.sections:
        for line in section.lines:
            if any(ref.alias == "r1" and ref.document_id for ref in line.basis):
                assert any(label in line.text for label in ("未齐", "未完整", "不完整", "成员未全", "尚未"))
