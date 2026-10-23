"""Pure policy, eight-section proposals, scoring and reversible expiration checks."""

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.memory2.archive import archive_changes, plan_archives
from mingjing_core.memory2.consent_text import has_storage_optout
from mingjing_core.memory2.contracts import (
    Confirmation,
    MemoryFact,
    MemoryScope,
    MemorySettings,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.mutations import apply_plan
from mingjing_core.memory2.reflection import (
    ChartSummary,
    ProfileItem,
    reflection_candidates,
)
from mingjing_core.memory2.scoring import decay_factor, importance_score
from mingjing_core.memory2.sensitivity import classify_sensitivity, decide_policy
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime(2026, 10, 21, 0, tzinfo=UTC)
SCOPE = MemoryScope("synthetic-owner", "synthetic-person-id")
CLOCK = FrozenClock(NOW)


def pair(text="我想学习画画。", kind="background", *, identity="fact", at=NOW, **kwargs):
    source = MemorySource("source-" + identity, SCOPE.owner_id, SCOPE.subject_id, text, at)
    anchor = SourceAnchor(source.id, 1, 0, len(text), text)
    fact = MemoryFact(
        identity, SCOPE.owner_id, SCOPE.subject_id, kind, text, (source.id,), at, at, anchors=(anchor,), **kwargs
    )
    return source, fact


def snapshot(*pairs):
    return MemorySnapshot(SCOPE, tuple(fact for _, fact in pairs), tuple(source for source, _ in pairs))


def decision(text, *, kind="background", **kwargs):
    source, fact = pair(text, kind)
    state = MemorySnapshot(SCOPE, sources=(source,))
    return decide_policy(state, fact, scope=SCOPE, clock=CLOCK, **kwargs)


@pytest.mark.parametrize(
    "text",
    [
        "不要把这个存成记忆。",
        "请勿存储我的近况。",
        "别放进档案。",
        "不允许归档这件事。",
        "不用记下。",
        "不准保存。",
        "此事不入长期记忆。",
        "这条别存。",
        "我不愿记录这件事。",
        "不要存入用户记忆。",
        "别加入长期记忆。",
        "禁止记录我的近况。",
        "这件事不能保存。",
        "本次不留存。",
        "无需记录这段。",
        "不要写进档案。",
        "别把这件事加入记忆。",
        "我不想保存。",
        "别存成记忆。",
        "不保存这段话。",
    ],
)
def test_storage_refusal(text):
    assert has_storage_optout(text)
    assert decision(text).action == "stop"


@pytest.mark.parametrize(
    "text",
    [
        "不要提醒我也不要保存这段。",
        "我不是说不要保存但现在这段别存。",
        "我没有要求别存不过这次不要记录。",
        "别再提醒我这个目标并且禁止存储。",
        "我没说不要记录然而现在不存这条。",
    ],
)
def test_real_storage_refusal_survives_reminder_and_negated_prefix(text):
    assert has_storage_optout(text)
    assert decision(text).action == "stop"


@pytest.mark.parametrize(
    "text",
    [
        "别忘记我想学习画画。",
        "不要忘了记住目标。",
        "不用每次提醒，记住我的目标。",
        "别再提醒我，记住目标。",
        "我没有说不要保存。",
        "我没说别记录。",
        "按钮写着‘不要保存’。",
        "标签上是“禁止记录”。",
        "我喜欢看记忆主题的小说。",
        "我不需要咖啡，喜欢绿茶。",
        "不要给建议，记住我想读书。",
        "不要让我忘了，记住这件事。",
        "我不是说不用记录。",
        "我没有要求别归档。",
        "我并非不让你记住。",
        "我喜欢‘不保存’这个按钮文案。",
        "不用解释术语，记住偏好即可。",
        "别重复提醒我，记住我想学画画。",
        "我想保存这条目标。",
        "不用担心，记住我最近在读书。",
    ],
)
def test_non_storage_negations_and_quotes(text):
    assert not has_storage_optout(text)
    assert decision(text).action == "save"


@pytest.mark.parametrize(
    "category,text",
    [
        ("health", "我在按医嘱服用药物。"),
        ("health", "我的体检发现结节。"),
        ("finance", "我的房贷还有八十万。"),
        ("finance", "我欠银行二十万。"),
        ("sexual_orientation", "我是泛性恋。"),
        ("religion", "我已受洗。"),
        ("politics", "我有自己的政治倾向。"),
        ("legal", "我收到了法院传票。"),
        ("third_party", "我室友的出生时间是清晨。"),
        ("third_party", "我朋友的工资是每月两万元。"),
    ],
)
def test_rules_and_model_hints_take_stricter_category(category, text):
    result = decision(text, model_hint=("public",))
    assert result.action == "proposal" and category in result.categories
    assert result.ask_required and result.question_key


def test_unknown_hint_stays_sensitive_and_cannot_be_preapproved_by_unknown_label():
    result = decision("我喜欢画画。", settings=MemorySettings({"model_sensitive"}), model_hint=("unknown-label",))
    assert result.action == "proposal" and result.categories == ("model_sensitive",)


@pytest.mark.parametrize("hint", ["secret", "credential", "password", "密码", "密钥", "身份证", "银行卡"])
def test_secret_model_hint_is_never_downgraded_to_confirmable_memory(hint):
    assert decision("这是模型识别出的合成受保护值。", model_hint=(hint,)).action == "reject"


def test_birth_data_and_credentials_have_dedicated_policy():
    assert decision("我只知道自己大约清晨出生。").action == "profile_confirm"
    assert decision("我的出生地点是合成小城。").action == "profile_confirm"
    assert decision("我的密码是合成例子。").action == "reject"
    assert classify_sensitivity("我的生日是六月一日。", subject_role="other").categories == ("third_party",)
    assert decision("我住在合成小城。", kind="profile").action == "save"


@pytest.mark.parametrize(
    "field,value",
    [
        ("section", True),
        ("confidence", True),
        ("confidence", float("nan")),
        ("confidence", "1"),
        ("pinned", 1),
        ("edited_by_user", 0),
        ("id", 1),
        ("source_ids", "source"),
        ("fact_ids", (1,)),
        ("fact_ids", ("same", "same")),
    ],
)
def test_profile_contract_rejects_malformed_boundary(field, value):
    arguments = dict(id="profile", section=2, text="合成条目。")
    arguments[field] = value
    with pytest.raises(ValueError):
        ProfileItem(**arguments)


@pytest.mark.parametrize(
    "field,value",
    [
        ("trusted", 1),
        ("method_version", 42),
        ("stability", True),
        ("source_ids", "source"),
        ("fact_ids", (True,)),
        ("basis_aliases", (42,)),
        ("scope", {"owner_id": "other"}),
    ],
)
def test_chart_contract_rejects_malformed_boundary(field, value):
    state = profile_state()
    with pytest.raises(ValueError):
        chart(state, **{field: value})


def test_declined_bound_consent_overrides_category_preapproval():
    source, fact = pair("我确诊了哮喘。")
    state = MemorySnapshot(SCOPE, sources=(source,))
    consent = Confirmation(
        SCOPE, source.id, 1, fact.anchors[0].quote_fingerprint, frozenset({"health"}), "declined", NOW
    )
    result = decide_policy(
        state, fact, scope=SCOPE, clock=CLOCK, settings=MemorySettings({"health"}), confirmation=consent
    )
    assert result.action == "stop"


@pytest.mark.parametrize("offset", [-1, 1])
def test_future_or_reverse_time_is_rejected(offset):
    source, fact = pair()
    changed = replace(fact, recorded_at=NOW + timedelta(seconds=offset))
    with pytest.raises(MemoryGuardError, match="fact_time_invalid"):
        decide_policy(MemorySnapshot(SCOPE, sources=(source,)), changed, scope=SCOPE, clock=CLOCK)


def profile_state():
    return snapshot(
        pair("我住在合成甲城。", "profile", identity="basic"),
        pair("我最近在学习陶艺。", identity="life"),
        pair("我希望完成一部小说。", "goal", identity="goal"),
        pair("小甲是我的朋友。", "relationship", identity="person"),
        pair("我喜欢绿茶。", "preference", identity="pref"),
        pair("我喜欢回答简洁。", "communication", identity="communication"),
        pair("我下个月要参加读书会。", "event", identity="event", event_at=NOW + timedelta(days=30)),
    )


def chart(state, **kwargs):
    values = dict(
        id="chart-v1",
        scope=SCOPE,
        text="太阳位置的合成学习摘要。",
        fact_ids=("basic",),
        source_ids=(state.fact("basic").source_ids[0],),
        basis_aliases=("〔c1〕", "〔r2〕"),
        method_version="synthetic-v1",
        stability="uncertain",
        trusted=True,
    )
    values.update(kwargs)
    return ChartSummary(**values)


def test_eight_sections_are_only_source_bound_proposals():
    state = profile_state()
    proposals = reflection_candidates(state, scope=SCOPE, clock=CLOCK, chart_summaries=(chart(state),))
    assert [item.section for item in proposals] == list(range(1, 9))
    assert all(item.action == "proposal" and item.origin == "reflection" for item in proposals)
    assert all(item.fact_ids and item.source_ids for item in proposals)
    assert proposals[6].basis_aliases == ("〔c1〕", "〔r2〕")
    assert proposals[6].stability == "uncertain"
    assert len(state.facts) == 7 and all(item.origin == "user" for item in state.facts)
    assert all("text=" not in repr(item) for item in proposals)


@pytest.mark.parametrize(
    "change",
    [
        {"trusted": False},
        {"stability": "guessed"},
        {"method_version": ""},
        {"basis_aliases": ("〔f1〕",)},
        {"fact_ids": ("missing",)},
        {"source_ids": ("other",)},
        {"scope": MemoryScope("other", SCOPE.subject_id)},
    ],
)
def test_untrusted_or_unanchored_charts_never_enter_section_seven(change):
    state = profile_state()
    result = reflection_candidates(state, scope=SCOPE, clock=CLOCK, chart_summaries=(chart(state, **change),))
    assert 7 not in {item.section for item in result}


def test_user_pinned_and_edited_items_cannot_be_overwritten():
    state = profile_state()
    current = (
        ProfileItem("pin", 5, "用户保留的原文", pinned=True),
        ProfileItem("edit", 5, "用户改写的原文", edited_by_user=True),
    )
    result = reflection_candidates(state, current, scope=SCOPE, clock=CLOCK)
    proposed = next(item for item in result if item.section == 5)
    assert proposed.target_item_id is None and proposed.protected_item_ids == ("pin", "edit")
    assert current[0].text == "用户保留的原文" and current[1].text == "用户改写的原文"


@pytest.mark.parametrize("flag", ["revoked", "incognito", "optout"])
def test_unavailable_source_does_not_reappear_in_reflection_or_archive(flag):
    state = snapshot(pair("我今天参加合成活动。", "event", event_end=NOW))
    state = replace(state, sources=(replace(state.sources[0], **{flag: True}),))
    assert reflection_candidates(state, scope=SCOPE, clock=CLOCK) == ()
    assert archive_changes(state, scope=SCOPE, clock=CLOCK) == ()


@pytest.mark.parametrize("days,factor", [(0, 1), (180, 0.5), (360, 0.25), (-1, 1)])
def test_decay_has_exact_180_day_half_life(days, factor):
    _, fact = pair(at=NOW - timedelta(days=days))
    assert decay_factor(fact, clock=CLOCK) == pytest.approx(factor)
    assert importance_score(fact, clock=CLOCK) == pytest.approx(0.5 * factor)


@pytest.mark.parametrize("kind", ["goal", "constraint"])
def test_targets_and_constraints_do_not_decay(kind):
    _, fact = pair(kind=kind, at=NOW - timedelta(days=3650))
    assert decay_factor(fact, clock=CLOCK) == 1


@pytest.mark.parametrize("half_life", [0, -1, True, float("nan"), float("inf")])
def test_invalid_half_life_is_rejected(half_life):
    _, fact = pair()
    with pytest.raises(ValueError):
        decay_factor(fact, clock=CLOCK, half_life_days=half_life)


def test_archive_requires_explicit_deadline_and_undo_restores_every_fact_field():
    state = snapshot(
        pair("我已参加合成活动。", "event", event_end=NOW, pinned=True, edited=True),
        pair("我过去参加过合成活动。", "event", identity="no-deadline", event_at=NOW - timedelta(days=7)),
        pair("我下周参加合成活动。", "event", identity="future", event_end=NOW + timedelta(days=7)),
    )
    plan = plan_archives(state, scope=SCOPE, clock=CLOCK, operation_id="archive-roundtrip")
    assert len(plan.changes) == 1 and plan.changes[0].id == "fact"
    applied = apply_plan(state, plan, clock=CLOCK).snapshot
    assert applied.fact("fact").status == "archived" and len(applied.facts) == 3
    assert applied.fact("fact").text == state.fact("fact").text
    restored = undo_plan(applied, plan, operation_id="undo-roundtrip").snapshot.fact("fact")
    assert all(getattr(restored, item.name) == getattr(state.fact("fact"), item.name) for item in fields(MemoryFact))
