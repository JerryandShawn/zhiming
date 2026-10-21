"""Eight sections render current source-bound content literally and preserve user protections."""

from dataclasses import asdict, replace
from datetime import timedelta
from typing import Any

import pytest

from mingjing_core.application.reflection_v3 import ReflectionEffects, ReflectionError
from mingjing_core.memory2.contracts import MemoryScope

from .calendar_acceptance_support_mod import SCOPE, bundle, profile, shown, view, wording

TITLES = (
    "称呼与基本情况",
    "现在的生活",
    "在意的事与目标",
    "重要的人",
    "偏好与禁忌",
    "沟通偏好",
    "命理档案摘要",
    "正在跟进",
)


def assert_empty(data: Any, document: Any = None, **overrides: Any) -> None:
    try:
        result = view(data, document, **overrides)
    except ReflectionError as error:
        assert data.snapshot.sources[0].text not in str(error)
        return
    assert tuple(section.number for section in result.sections) == tuple(range(1, 9))
    assert not shown(result)


def test_exact_eight_sections_follow_original_design_order() -> None:
    result = view(bundle())
    assert tuple(section.number for section in result.sections) == tuple(range(1, 9))
    assert tuple(section.title for section in result.sections) == TITLES
    assert len(shown(result)) == 1


@pytest.mark.parametrize("section", (1, 2, 3, 4, 5, 6, 8))
def test_current_bound_item_remains_in_its_own_section(section: int) -> None:
    data = bundle()
    result = view(data, profile(data, section=section))
    assert len(shown(result)) == 1
    assert shown(result)[0].section == section and shown(result)[0].text == data.snapshot.facts[0].text


@pytest.mark.parametrize("authority", (None, 0, 4, 6))
def test_missing_or_stale_profile_authority_cannot_render_content(authority: int | None) -> None:
    assert_empty(bundle(), current_profile_revision=authority)


@pytest.mark.parametrize(
    "changes",
    (
        {"snapshot_revision": 3},
        {"source_epoch": 2},
        {"active": False},
        {"scope": MemoryScope("synthetic-other-owner", SCOPE.subject_id)},
    ),
)
def test_profile_document_depends_on_current_snapshot_scope_epoch(changes: dict[str, Any]) -> None:
    data = bundle()
    assert_empty(data, replace(profile(data), **changes))


@pytest.mark.parametrize("protection", ("pinned", "edited_by_user"))
@pytest.mark.parametrize("source_changes", ({"revoked": True}, {"active": False}, {"incognito": True}, {"revision": 2}))
def test_pinned_or_edited_does_not_restore_withdrawn_or_changed_source(
    protection: str, source_changes: dict[str, Any]
) -> None:
    data = bundle()
    document = profile(data)
    entry = document.entries[0]
    document = replace(document, entries=(replace(entry, item=replace(entry.item, **{protection: True})),))
    snapshot = replace(data.snapshot, sources=(replace(data.snapshot.sources[0], **source_changes),))
    assert_empty(data, document, snapshot=snapshot)


@pytest.mark.parametrize(
    "changes",
    (
        {"status": "retired"},
        {"status": "deleted"},
        {"status": "archived"},
        {"origin": "assistant_claim"},
        {"source_valid": False},
    ),
)
def test_invalid_fact_cannot_become_about_me_user_fact(changes: dict[str, Any]) -> None:
    data = bundle()
    snapshot = replace(data.snapshot, facts=(replace(data.snapshot.facts[0], **changes),))
    assert_empty(data, snapshot=snapshot)


def test_expired_or_not_yet_valid_facts_are_not_current_profile() -> None:
    data = bundle()
    for changes in ({"valid_to": data.clock.now()}, {"valid_from": data.clock.now() + timedelta(seconds=1)}):
        snapshot = replace(data.snapshot, facts=(replace(data.snapshot.facts[0], **changes),))
        assert_empty(data, snapshot=snapshot)


@pytest.mark.parametrize("change", ("quote", "revision", "range", "missing"))
def test_profile_anchor_must_match_current_fact_and_original_source(change: str) -> None:
    data = bundle()
    document = profile(data)
    entry, anchor = document.entries[0], document.entries[0].anchors[0]
    changes = {
        "quote": {"quote": wording("second")},
        "revision": {"revision": 2},
        "range": {"start": 1},
    }
    anchors = () if change == "missing" else (replace(anchor, **changes[change]),)
    assert_empty(data, replace(document, entries=(replace(entry, anchors=anchors),)))


def test_profile_cannot_use_assistant_original_as_user_quote() -> None:
    data = bundle()
    source = replace(data.snapshot.sources[0], role="assistant", origin="assistant")
    assert_empty(data, snapshot=replace(data.snapshot, sources=(source,)))


def test_source_quote_edit_and_at_edit_invalidate_profile_even_without_pin_bypass() -> None:
    data = bundle()
    for changes in ({"text": wording("source_mutated")}, {"at": data.snapshot.sources[0].at - timedelta(seconds=1)}):
        assert_empty(data, snapshot=replace(data.snapshot, sources=(replace(data.snapshot.sources[0], **changes),)))


def test_markdown_and_html_are_literal_without_new_headings_links_or_script() -> None:
    data = bundle(text_key="markdown")
    result = view(data)
    assert len(shown(result)) == 1 and shown(result)[0].text == wording("markdown")
    assert "<script>" not in result.markdown
    assert "**literal**" not in result.markdown and "[reference](" not in result.markdown
    assert "`code`" not in result.markdown and "\n## heading" not in result.markdown
    assert len([line for line in result.markdown.splitlines() if line.startswith("## ")]) == 8
    assert "literal" in result.markdown and "example.invalid" in result.markdown.replace("\\.", ".")


def test_analysis_keeps_inference_label_separate_from_user_original() -> None:
    data = bundle()
    document = profile(data)
    entry = replace(
        document.entries[0], origin="analysis", item=replace(document.entries[0].item, text=wording("analysis"))
    )
    result = view(data, replace(document, entries=(entry,)))
    assert shown(result)[0].origin == "analysis"
    assert "推测" in result.markdown and "不是用户原话" in result.markdown


def test_section_seven_cannot_trust_a_host_boolean_or_unverified_chart_label() -> None:
    data = bundle()
    document = profile(data, section=7)
    document = replace(document, entries=(replace(document.entries[0], origin="chart_unverified"),))
    result = view(data, document)
    assert not shown(result)
    assert "尚无权威契约验证" in result.markdown


def test_manual_and_pinned_current_lines_are_visible_but_do_not_gain_effects() -> None:
    data = bundle()
    document = profile(data)
    entry = replace(document.entries[0], item=replace(document.entries[0].item, pinned=True, edited_by_user=True))
    result = view(data, replace(document, entries=(entry,)))
    assert shown(result)[0].pinned is True and shown(result)[0].edited_by_user is True
    assert "用户编辑" in result.markdown
    assert all(type(value) is int and value == 0 for value in asdict(result.effects).values())


@pytest.mark.parametrize("field", ("source_ids", "fact_ids"))
def test_profile_item_cannot_omit_its_source_or_fact_dependency(field: str) -> None:
    data = bundle()
    document = profile(data)
    entry = document.entries[0]
    item = replace(entry.item, **{field: ()})
    assert_empty(data, replace(document, entries=(replace(entry, item=item),)))


@pytest.mark.parametrize("change", ("inactive", "foreign_scope"))
def test_entry_lifecycle_and_scope_do_not_inherit_authority_from_parent(change: str) -> None:
    data = bundle()
    document = profile(data)
    changes = {"active": False} if change == "inactive" else {"scope": MemoryScope("synthetic-other", SCOPE.subject_id)}
    assert_empty(data, replace(document, entries=(replace(document.entries[0], **changes),)))


@pytest.mark.parametrize("text_key", ("sensitive", "birth", "optout"))
def test_rendering_does_not_invent_missing_sensitive_or_profile_confirmation(text_key: str) -> None:
    assert_empty(bundle(text_key=text_key))


def test_section_seven_is_not_authorized_by_user_fact_origin_label_either() -> None:
    data = bundle()
    assert_empty(data, profile(data, section=7))


@pytest.mark.parametrize(
    "field", ("model_calls", "queue_writes", "fact_writes", "profile_writes", "notifications", "deletes")
)
@pytest.mark.parametrize("value", (True, 1, -1, 0.0))
def test_effects_cannot_be_nonzero_or_false_zero(field: str, value: object) -> None:
    with pytest.raises(ReflectionError):
        ReflectionEffects(**{field: value})
