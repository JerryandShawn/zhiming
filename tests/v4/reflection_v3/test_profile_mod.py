"""Eight-section about-me projection rejects stale sources before rendering even pinned items."""

from dataclasses import replace

import pytest

from mingjing_core.application.reflection_v3 import ReflectionEffects, ReflectionError, render_about_me
from mingjing_core.memory2.contracts import MemoryScope, MemorySettings

from .support_mod import AT, SCOPE, TEXTS, changed_source, context, fact, profile


def render(document, values, **kwargs):
    args = {key: values[key] for key in ("snapshot", "scope", "clock")}
    return render_about_me(document, **args, current_profile_revision=document.revision, **kwargs)


def test_exactly_eight_sections_preserve_user_text_and_show_bound_original_quotes():
    values = context()
    document = profile(values["snapshot"])
    view = render(document, values)
    assert len(view.sections) == 8 and view.sections[1].lines[0].anchors == document.entries[0].anchors
    assert "用户原话〔m1〕" in view.markdown and "依据用户事实的条目" in view.markdown
    assert view.effects == ReflectionEffects() and "暂无当前有效条目" in view.markdown


@pytest.mark.parametrize(
    "change",
    [{"revoked": True}, {"active": False}, {"incognito": True}, {"optout": True}, {"revision": 2}, {"text": ""}],
)
@pytest.mark.parametrize("protected", ["pinned", "edited"])
def test_source_withdrawal_also_hides_pinned_and_user_edited_entries(change, protected):
    values = context()
    document = profile(values["snapshot"], **{protected: True})
    result = render(document, changed_source(values, **change))
    assert all(not section.lines for section in result.sections)
    assert TEXTS["background"] not in result.markdown


@pytest.mark.parametrize(
    "field,value", [("revision", 6), ("snapshot_revision", 4), ("source_epoch", 5), ("active", False)]
)
def test_stale_profile_document_returns_eight_empty_sections(field, value):
    values = context()
    document = profile(values["snapshot"])
    current = replace(document, **{field: value})
    result = render_about_me(
        current,
        snapshot=values["snapshot"],
        scope=SCOPE,
        clock=values["clock"],
        current_profile_revision=document.revision,
    )
    assert (
        all(not section.lines for section in result.sections) and "current_profile_snapshot_required" in result.warnings
    )


@pytest.mark.parametrize("field", ["document", "entry"])
def test_foreign_profile_is_a_fixed_error_without_body_or_id(field):
    values = context()
    document = profile(values["snapshot"])
    foreign = MemoryScope("foreign-owner", SCOPE.subject_id)
    current = (
        replace(document, scope=foreign)
        if field == "document"
        else replace(document, entries=(replace(document.entries[0], scope=foreign),))
    )
    with pytest.raises(ReflectionError) as error:
        render(current, values)
    assert "foreign-owner" not in str(error.value) and TEXTS["background"] not in str(error.value)


@pytest.mark.parametrize("kind", ["note", "assistant_claim", "chart_interpretation", "chart_summary"])
def test_inferred_and_assistant_notes_cannot_be_called_user_facts(kind):
    values = context(fact(kind=kind))
    result = render(profile(values["snapshot"]), values)
    assert all(not section.lines for section in result.sections)


def test_analysis_is_explicitly_separate_and_html_markdown_are_literal():
    values = context(fact(text_key="markup"))
    result = render(profile(values["snapshot"], origin="analysis"), values)
    assert "推测（不是用户原话）" in result.markdown
    assert "<script>" not in result.markdown and "&lt;script&gt;" in result.markdown
    assert "[jump](javascript:evil)" not in result.markdown and "\n## injected" not in result.markdown


def test_old_trusted_chart_item_stays_unverified_section_seven():
    values = context()
    document = profile(values["snapshot"], section=7, origin="chart_unverified")
    result = render(document, values)
    assert not result.sections[6].lines and "尚无权威契约验证" in result.markdown


@pytest.mark.parametrize("change", ["sources", "facts", "anchors", "future_update"])
def test_source_less_or_misbound_or_future_profile_item_is_not_shown(change):
    values = context()
    document = profile(values["snapshot"])
    entry = document.entries[0]
    if change == "sources":
        entry = replace(entry, item=replace(entry.item, source_ids=()))
    elif change == "facts":
        entry = replace(entry, item=replace(entry.item, fact_ids=()))
    elif change == "anchors":
        entry = replace(entry, anchors=())
    else:
        entry = replace(entry, item=replace(entry.item, updated_at=AT.replace(year=2027)))
    result = render(replace(document, entries=(entry,)), values)
    assert all(not section.lines for section in result.sections)


def test_sensitive_category_needs_current_explicit_consent_and_birth_flow_cannot_be_bypassed():
    values = context(fact(text_key="health"))
    document = profile(values["snapshot"])
    assert all(not section.lines for section in render(document, values).sections)
    result = render(document, values, settings=MemorySettings(frozenset({"health"})))
    assert result.sections[1].lines
    values = context(fact(text_key="birth"))
    result = render(profile(values["snapshot"]), values, settings=MemorySettings(frozenset({"health"})))
    assert all(not section.lines for section in result.sections)
