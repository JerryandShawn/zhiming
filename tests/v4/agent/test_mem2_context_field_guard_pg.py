"""Native PG snapshot fields survive a downstream profile projection boundary."""

import json

import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_fact_guards import preserve_field_facts
from mingjing_core.agent.context_layers import AliasBook, fact_layer, json_item
from mingjing_core.agent.context_types import ContextLayer
from mingjing_core.timekit.clock import get_clock

from .test_context_pg import context_memory_fixture as source_fixture
from .test_context_pg import receive


@pytest.fixture(name="memory")
def memory_fixture(p2_repo, monkeypatch):
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def setup_profile(memory, field, value):
    text = f"请保存我的{field}为{value}"
    source = receive(memory, text, "birth-source")
    fact = memory.save_fact("alice", "self", source["id"], text, "profile", field=field, value=value)
    ordinary = receive(memory, "请保存我喜欢喝茶", "ordinary-source")
    preference = memory.save_fact("alice", "self", ordinary["id"], ordinary["content"], "preference")
    doc = memory.repo.put(
        "alice",
        "profile_doc",
        "synthetic-confirmed-profile",
        {
            "text": "合成已确认画像摘要",
            "confirmed_by_user": True,
            "fact_ids": [fact["id"], preference["id"]],
            "source_ids": [source["id"], ordinary["id"]],
        },
        expected_revision=0,
    )
    current = receive(memory, "请参考已确认资料", "current-source")
    engine = ContextEngine(memory, "合成系统", clock=get_clock())
    snapshot = engine._sources("alice", "self", current["id"], None, (), None, None)
    return fact, preference, doc, current, engine, snapshot


@pytest.mark.parametrize(
    "field,value,notice",
    [
        ("birth.precision", "unknown", True),
        ("birth.time_unknown", True, True),
        ("birth.precision", "exact", False),
        ("birth.time_unknown", False, False),
        ("gender", "女", False),
    ],
)
def test_profile_representation_cannot_suppress_native_field_or_birth_notice(memory, field, value, notice):
    fact, preference, doc, _, _, snapshot = setup_profile(memory, field, value)
    aliases = AliasBook()
    # A real stored profile enters the pure renderer as an already projected item.
    # The module's profile loader is deliberately not imported before its merge gate.
    profile_item = json_item(doc["id"], "画像", {"text": doc["text"]}, required=True, sources=tuple(doc["source_ids"]))
    rendered = preserve_field_facts(snapshot, aliases, ContextLayer("L2", (profile_item,)))
    assert [item.key for item in rendered.items] == [doc["id"], fact["id"]]
    assert preference["id"] not in {item.key for item in rendered.items}
    actual = rendered.items[-1]
    payload = json.loads(actual.messages[0].content.splitlines()[1])
    assert payload["text"] == fact["content"] and actual.required
    assert ("birth_time_notice" in payload) is notice
    assert aliases.values[payload["alias"]] == {"kind": "fact", "id": fact["id"], "revision": fact["revision"]}
    assert preserve_field_facts(snapshot, aliases, rendered) == rendered


def test_field_entry_is_rebuilt_from_authority_not_inferred_profile_text(memory):
    fact, _, _, _, _, snapshot = setup_profile(memory, "birth.time_unknown", True)
    rewritten = json_item(fact["id"], "画像", {"text": "画像推断出生时刻准确"}, required=False)
    result = preserve_field_facts(snapshot, AliasBook(), ContextLayer("L2", (rewritten,)))
    payload = json.loads(result.items[0].messages[0].content.splitlines()[1])
    assert payload["text"] == fact["content"] and "birth_time_notice" in payload
    assert result.items[0].required


def test_guard_never_restores_withdrawn_or_other_owner_fields_from_profile_ids(memory):
    fact, _, doc, current, engine, snapshot = setup_profile(memory, "birth.time_unknown", True)
    memory.repo.delete("alice", "fact", fact["id"], expected_revision=fact["revision"])
    source = memory.receive("bob", content="请保存我的birth.time_unknown为True", source_id="bob-birth")
    other = memory.save_fact(
        "bob", "self", source["id"], source["content"], "profile", field="birth.time_unknown", value=True
    )
    fresh = engine._sources("alice", "self", current["id"], None, (), None, None)
    assert fact["id"] not in {row["id"] for row in fresh.facts}
    assert other["id"] not in {row["id"] for row in fresh.facts}
    layer = ContextLayer("L2", (json_item(doc["id"], "画像", {"text": doc["text"]}, required=True),))
    result = preserve_field_facts(fresh, AliasBook(), layer)
    assert result == layer
    assert fact["id"] in {row["id"] for row in snapshot.facts}


def test_mainline_context_invokes_guard_and_retains_original_alias_and_source_versions(memory, monkeypatch):
    import mingjing_core.agent.context_layers as layers

    fact, _, _, current, engine, snapshot = setup_profile(memory, "birth.time_unknown", True)
    calls = []
    original = layers.preserve_field_facts

    def observed(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(layers, "preserve_field_facts", observed)
    built = engine.build("alice", current["id"])
    assert calls == [1]
    l2 = next(layer for layer in built.budget.layers if layer.name == "L2")
    assert any("birth_time_notice" in message.content for item in l2.items for message in item.messages)
    assert built.injected_versions["fact:" + fact["id"]] == fact["revision"]
    assert (
        built.injected_versions["message:" + fact["source_refs"][0]["message_id"]] == fact["source_refs"][0]["version"]
    )
    book = AliasBook()
    unchanged = fact_layer(snapshot, book)
    assert preserve_field_facts(snapshot, book, unchanged) == unchanged
