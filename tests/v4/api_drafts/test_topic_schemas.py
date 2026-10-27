"""Offline tests of proposed documentation contracts, never HTTP acceptance."""

from copy import deepcopy
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS = {
    path.stem: path.read_text(encoding="utf-8")
    for path in (ROOT / "docs/v4/contracts").glob("api_*_draft.md")
}
SCHEMAS = {
    name: json.loads(re.findall(r"```json\n(.*?)\n```", text, re.S)[0])
    for name, text in DOCUMENTS.items()
}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)
TOPICS = [name for name in SCHEMAS if name != "api_modules_common_draft"]
EXAMPLES = [
    (name, example) for name in TOPICS for example in SCHEMAS[name]["x-examples"]
]
ENDPOINTS = [
    (name, endpoint) for name in TOPICS for endpoint in SCHEMAS[name]["x-endpoints"]
]


def validator(topic, definition):
    schema = dict(SCHEMAS[f"api_{topic}_draft"], **{"$ref": f"#/$defs/{definition}"})
    return Draft202012Validator(
        schema, registry=REGISTRY, format_checker=FormatChecker()
    )


def example(topic, definition):
    return deepcopy(
        next(
            item["value"]
            for item in SCHEMAS[f"api_{topic}_draft"]["x-examples"]
            if item["schema"] == definition
        )
    )


@pytest.mark.parametrize("name", list(SCHEMAS))
def test_each_embedded_schema_is_valid_and_explicitly_unimplemented(name):
    Draft202012Validator.check_schema(SCHEMAS[name])
    assert "草稿，未冻结、未实现" in DOCUMENTS[name]


@pytest.mark.parametrize("name,item", EXAMPLES)
def test_every_documented_request_and_response_example_resolves_locally(name, item):
    topic = name.removeprefix("api_").removesuffix("_draft")
    validator(topic, item["schema"]).validate(item["value"])


@pytest.mark.parametrize("name,endpoint", ENDPOINTS)
def test_endpoint_contract_has_examples_safe_errors_and_write_revision(name, endpoint):
    schema = SCHEMAS[name]
    example_names = {item["schema"] for item in schema["x-examples"]}
    common_codes = SCHEMAS["api_modules_common_draft"]["$defs"]["Error"]["properties"][
        "error"
    ]["properties"]["code"]["enum"]
    assert endpoint["request"] in example_names
    assert endpoint["response"] in example_names
    assert set(endpoint["errors"]) <= set(common_codes)
    if endpoint["method"] != "GET":
        request = schema["$defs"][endpoint["request"]]
        assert {"request_id", "expected_revision"} <= set(request["required"])
        assert endpoint["revision_resource"] != "none"
        assert "UNKNOWN_RESULT" in endpoint["errors"]


WRITES = [(name, ep) for name, ep in ENDPOINTS if ep["method"] != "GET"]


@pytest.mark.parametrize("name,endpoint", WRITES)
@pytest.mark.parametrize("field", ["request_id", "expected_revision"])
def test_every_write_rejects_missing_identity_or_revision(name, endpoint, field):
    topic = name.removeprefix("api_").removesuffix("_draft")
    body = example(topic, endpoint["request"])
    del body[field]
    assert not validator(topic, endpoint["request"]).is_valid(body)


@pytest.mark.parametrize("name,endpoint", WRITES)
@pytest.mark.parametrize("injected", ["owner", "runtime", "provider", "undo_token"])
def test_every_write_rejects_privileged_fields(name, endpoint, injected):
    topic = name.removeprefix("api_").removesuffix("_draft")
    body = example(topic, endpoint["request"])
    body[injected] = "synthetic:untrusted"
    assert not validator(topic, endpoint["request"]).is_valid(body)


@pytest.mark.parametrize("name,endpoint", WRITES)
@pytest.mark.parametrize("revision", [-1, True, "1"])
def test_every_write_rejects_invalid_revision(name, endpoint, revision):
    topic = name.removeprefix("api_").removesuffix("_draft")
    body = example(topic, endpoint["request"])
    body["expected_revision"] = revision
    assert not validator(topic, endpoint["request"]).is_valid(body)


@pytest.mark.parametrize("definition", ["PatchSpace", "PatchTopic"])
def test_empty_patch_is_rejected(definition):
    body = example("spaces_topics", definition)
    body["patch"] = {}
    assert not validator("spaces_topics", definition).is_valid(body)


def test_custom_spaces_are_allowed_but_case_link_must_be_explicit():
    body = example("spaces_topics", "TopicList")
    body["items"][0]["space_id"] = "synthetic:custom-space"
    validator("spaces_topics", "TopicList").validate(body)
    body["items"][0]["status"] = "case"
    assert not validator("spaces_topics", "TopicList").is_valid(body)
    body["items"][0]["case_id"] = "synthetic:case1"
    validator("spaces_topics", "TopicList").validate(body)


@pytest.mark.parametrize(
    "kind,field",
    [
        ("rename", "title"),
        ("merge", "target_ids"),
        ("split", "message_ids"),
        ("move", "space_id"),
    ],
)
def test_organization_edits_require_kind_specific_fields(kind, field):
    edit = {"kind": kind, "target_id": "synthetic:t1"}
    assert not validator("organize", "PlanEdit").is_valid(edit)
    edit[field] = (
        ["synthetic:t2", "synthetic:t3"]
        if field in {"target_ids", "message_ids"}
        else "synthetic:new"
    )
    if kind == "split":
        edit["title"] = "合成拆分话题"
    validator("organize", "PlanEdit").validate(edit)


def test_split_rejects_topic_ids_in_place_of_source_messages():
    edit = {
        "kind": "split",
        "target_id": "synthetic:t1",
        "title": "合成",
        "target_ids": ["synthetic:t2", "synthetic:t3"],
    }
    assert not validator("organize", "PlanEdit").is_valid(edit)


@pytest.mark.parametrize(
    "definition,status", [("ApplyResult", "queued"), ("RevertResult", "updated")]
)
def test_applied_or_reverted_response_cannot_masquerade_as_queued_or_updated(
    definition, status
):
    body = example("organize", definition)
    body["receipt"]["write_status"] = status
    assert not validator("organize", definition).is_valid(body)


def test_apply_result_provides_change_id_for_exact_undo():
    body = example("organize", "ApplyResult")
    del body["change_id"]
    assert not validator("organize", "ApplyResult").is_valid(body)


@pytest.mark.parametrize("accepted", [False, 1, "true", None])
def test_review_cannot_be_implicitly_approved(accepted):
    body = example("organize", "Review")
    body["accepted"] = accepted
    assert not validator("organize", "Review").is_valid(body)


@pytest.mark.parametrize(
    "field,value",
    [("reviewed_at", "2026-10-27"), ("accepted", True), ("owner", "synthetic:foreign")],
)
def test_apply_cannot_supply_its_own_trusted_receipt(field, value):
    body = example("organize", "Apply")
    body[field] = value
    assert not validator("organize", "Apply").is_valid(body)


@pytest.mark.parametrize("fingerprint", ["a" * 63, "z" * 64, "", None])
def test_apply_requires_exact_fingerprint_shape(fingerprint):
    body = example("organize", "Apply")
    body["plan_fingerprint"] = fingerprint
    assert not validator("organize", "Apply").is_valid(body)


@pytest.mark.parametrize(
    "precision,time,uncertainty,valid",
    [
        ("unknown", None, None, True),
        ("unknown", "12:00", None, False),
        ("exact", "12:00", None, True),
        ("exact", None, None, False),
        ("exact", "25:00", None, False),
        ("approximate", "12:00", 30, True),
        ("approximate", "12:00", None, False),
        ("approximate", "12:00", 0, False),
    ],
)
def test_birth_precision_has_no_invented_unknown_time(
    precision, time, uncertainty, valid
):
    body = example("profile", "BirthEdit")
    body["data"].update(
        precision=precision, birth_time=time, uncertainty_minutes=uncertainty
    )
    assert validator("profile", "BirthEdit").is_valid(body) is valid


def test_profile_invalid_calendar_dates_and_unconfirmed_edits_are_rejected():
    body = example("profile", "BirthEdit")
    body["data"]["birth_date"] = "2000-02-30"
    assert not validator("profile", "BirthEdit").is_valid(body)
    body = example("profile", "ValueEdit")
    body["confirmed"] = False
    assert not validator("profile", "ValueEdit").is_valid(body)


def test_p8_interpretation_section_is_read_only_in_view():
    body = example("profile", "ProfileView")
    body["entries"][0].update(section=7, read_only=False)
    assert not validator("profile", "ProfileView").is_valid(body)
    body["entries"][0]["read_only"] = True
    validator("profile", "ProfileView").validate(body)


@pytest.mark.parametrize("scope", ["entry_only", "source_segment", "everything"])
def test_memory_delete_scope_is_explicit(scope):
    body = example("profile", "DeleteMemory")
    body["scope"] = scope
    assert validator("profile", "DeleteMemory").is_valid(body) is (
        scope != "everything"
    )


def test_study_content_needs_references_and_progress_cannot_edit_it():
    body = example("study", "Lesson")
    body["citations"] = []
    assert not validator("study", "Lesson").is_valid(body)
    progress = example("study", "UpdateProgress")
    progress["content"] = "synthetic injection"
    assert not validator("study", "UpdateProgress").is_valid(progress)


def test_absent_progress_requires_zero_revision_and_pending_edit_has_no_change():
    body = example("study", "ProgressView")
    body["revision"] = 1
    assert not validator("study", "ProgressView").is_valid(body)
    edit = example("profile", "WriteResult")
    edit["receipt"]["write_status"] = "pending_confirmation"
    assert not validator("profile", "WriteResult").is_valid(edit)
    edit["change_id"] = None
    validator("profile", "WriteResult").validate(edit)


def test_case_upgrade_patch_requires_explicit_case_link():
    body = example("spaces_topics", "PatchTopic")
    body["patch"] = {"status": "case"}
    assert not validator("spaces_topics", "PatchTopic").is_valid(body)
    body["patch"]["case_id"] = "synthetic:case1"
    validator("spaces_topics", "PatchTopic").validate(body)


@pytest.mark.parametrize(
    "status", ["not_started", "in_progress", "completed", "knowledge_proved"]
)
def test_progress_status_is_not_assessment(status):
    body = example("study", "UpdateProgress")
    body["status"] = status
    assert validator("study", "UpdateProgress").is_valid(body) is (
        status != "knowledge_proved"
    )


def test_contracts_preserve_business_checks_that_schema_cannot_prove():
    required = {
        "organize": [
            "24小时",
            "additive-only",
            "QUALITY_GATE_CLOSED",
            "旧Q5",
            "null",
            "同ID对账",
        ],
        "profile": ["原文半开区间", "同意", "兼容待主线", "409保留草稿", "undo_token"],
        "spaces_topics": ["hidden", "/api/cases", "不删消息", "cursor"],
        "study": ["不形成用户事实", "revision=0", "不证明理解", "409保留草稿"],
    }
    for topic, terms in required.items():
        assert all(term in DOCUMENTS[f"api_{topic}_draft"] for term in terms)
