"""Versioned, stable context blocks with run-local aliases and a moving history window."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mingjing_core.memory.tokenize import tokenize
from mingjing_core.models.port import ChatMessage
from mingjing_core.timekit.clock import Clock
from mingjing_core.timekit.now_block import render_now_block

from .context_current import current_layer
from .context_types import BudgetPolicy, ContextItem, ContextLayer, SourceSnapshot


@dataclass
class AliasBook:
    values: dict[str, dict[str, str | int]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def add(self, prefix: str, kind: str, row: dict[str, Any]) -> str:
        for alias, value in self.values.items():
            if value["kind"] == kind and value["id"] == row["id"]:
                return alias
        ordinal = row.get("_context_ordinal") if prefix == "m" else None
        number = ordinal if type(ordinal) is int and ordinal > 0 else self.counters.get(prefix, 0) + 1
        alias = prefix + str(number)
        if alias in self.values:
            raise ValueError("Context alias identity conflict")
        self.counters[prefix] = max(self.counters.get(prefix, 0), number)
        self.values[alias] = {
            "kind": kind,
            "id": row["id"],
            "revision": row["revision"],
        }
        return alias


def json_item(
    key: str,
    tag: str,
    data: Any,
    *,
    required: bool = False,
    sources: tuple[str, ...] = (),
) -> ContextItem:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return ContextItem(
        key,
        (ChatMessage("system", f"<{tag}>\n{encoded}\n</{tag}>"),),
        required,
        source_ids=sources,
    )


def fact_layer(snapshot: SourceSnapshot, aliases: AliasBook) -> ContextLayer:
    from .context_profiles import profile_items

    items, represented = profile_items(snapshot, aliases)
    for row in sorted(snapshot.facts, key=lambda fact: (fact.get("kind") != "constraint", fact["id"])):
        if row["id"] in represented and row.get("kind") != "constraint":
            continue
        alias = aliases.add("f", "fact", row)
        data = {
            "alias": alias,
            "date": row.get("said_at") or row.get("valid_from"),
            "kind": row["kind"],
            "text": row["content"],
        }
        if (row.get("field") == "birth.precision" and row.get("value") == "unknown") or (
            row.get("field") == "birth.time_unknown" and row.get("value") is True
        ):
            data["birth_time_notice"] = "时辰还不确定，以下只看不依赖时柱的部分。"
        items.append(json_item(row["id"], "画像", data, required=True))
    return ContextLayer("L2", tuple(items))


def stable_layer(snapshot: SourceSnapshot, aliases: AliasBook) -> ContextLayer:
    items = []
    events = snapshot.extra_entities.get("feedback", ())
    for row in snapshot.extra_entities.get("case", ()):
        recent = [event for event in events if event.get("case_id") == row["id"]][-3:]
        data = {
            "alias": aliases.add("e", "case", row),
            "title": row.get("title", ""),
            "goal": row.get("state", {}).get("goal", ""),
            "status": row["status"],
            "events": [
                {
                    "alias": aliases.add("e", "feedback", event),
                    "kind": event.get("kind"),
                    "text": event.get("content", ""),
                    "at": event.get("occurred_at"),
                }
                for event in recent
            ],
        }
        items.append(
            json_item(
                row["id"],
                "进行中",
                data,
                sources=tuple(event["id"] for event in recent),
            )
        )
    return ContextLayer("L3_STABLE", tuple(items))


def history_layer(snapshot: SourceSnapshot, aliases: AliasBook, policy: BudgetPolicy) -> ContextLayer:
    groups: list[ContextItem] = []
    for row in snapshot.history:
        role = row.get("role")
        if role not in {"user", "assistant"} or role == "assistant" and not groups:
            continue
        alias = aliases.add("m", "message", row)
        content = f"〔{alias}〕 [{row.get('at', '')} {row.get('channel', '')}]\n{row['content']}"
        message = ChatMessage(role, content)
        if role == "assistant":
            old = groups[-1]
            groups[-1] = ContextItem(
                old.key,
                (*old.messages, message),
                source_ids=(*old.source_ids, row["id"]),
            )
        else:
            groups.append(ContextItem(row["id"], (message,), source_ids=(row["id"],)))
    rounds = snapshot.read_counts.get("thread_user_rounds", len(groups) + 1)
    start = max(
        0,
        (rounds - policy.history_rounds - 1) // policy.window_step * policy.window_step,
    )
    kept = max(0, rounds - start - 1)
    groups = groups[-kept:] if kept else []
    prefix = []
    if start or snapshot.read_counts.get("history_truncated", 0):
        prefix.append(
            json_item(
                "history-window",
                "线程窗口",
                {"window_start_round": start, "note": "更早的对话见检索"},
                required=True,
            )
        )
    summaries = snapshot.extra_entities.get("thread_summary", ())
    for row in summaries[-1:]:
        prefix.append(
            json_item(
                row["id"],
                "线程摘要",
                {"text": row.get("text") or row.get("summary", "")},
                sources=tuple(row.get("source_ids", [])),
            )
        )
    return ContextLayer("L5", tuple(prefix + groups))


def retrieval_layer(snapshot: SourceSnapshot, aliases: AliasBook, policy: BudgetPolicy) -> ContextLayer:
    items = []
    if snapshot.retrieval_time_filter:
        header = f'<相关记忆 time_filter="{snapshot.retrieval_time_filter}">\n'
        header += "时间命中的条目优先；time_match=false只是补充资料，不能当成该时段发生的事。"
        items.append(
            ContextItem(
                "time-filter",
                (ChatMessage("system", header),),
                True,
                source_ids=(snapshot.current["id"],),
            )
        )
    candidates = [(row.get("_retrieval_kind", "message"), row) for row in snapshot.retrieved]
    query = set(tokenize(snapshot.current["content"][:2000])[:32])
    derived = [(kind, row) for kind in ("note", "episode") for row in snapshot.extra_entities.get(kind, ())]
    ranked = sorted(
        derived,
        key=lambda pair: (
            -len(query.intersection(tokenize(pair[1].get("content") or pair[1].get("summary", "")))),
            pair[1]["id"],
        ),
    )
    candidates.extend(
        (kind, row)
        for kind, row in ranked
        if query.intersection(tokenize(row.get("content") or row.get("summary", "")))
    )
    for kind, row in candidates[: policy.search_limit]:
        prefix = {"message": "m", "fact": "f", "note": "n", "episode": "e"}[kind]
        alias = aliases.add(prefix, kind, row)
        value = {
            "alias": alias,
            "date": row.get("event_at") or row.get("at") or row.get("created_at"),
            "kind": kind,
            "source": "明镜（我之前说的）"
            if row.get("role") == "assistant"
            else row.get("channel", "明镜推测笔记" if kind == "note" else "情景摘要"),
            "valid": True,
            "text": row.get("content") or row.get("summary", ""),
        }
        if snapshot.retrieval_time_filter:
            value["time_match"] = row.get("_time_match", False)
        items.append(json_item(row["id"], "相关记忆", value))
    return ContextLayer("L4", tuple(items))


def volatile_layer(snapshot: SourceSnapshot, aliases: AliasBook) -> ContextLayer:
    items = []
    for kind in ("knowledge_gap", "followup", "reminder"):
        rows = sorted(
            snapshot.extra_entities.get(kind, ()),
            key=lambda row: (
                -row.get("priority", 0) if type(row.get("priority", 0)) is int else 0,
                row["id"],
            ),
        )
        for row in rows[:5]:
            alias = aliases.add("e", kind, row)
            data = {
                "alias": alias,
                "kind": kind,
                "topic": row.get("topic", ""),
                "text": row.get("question") or row.get("text") or row.get("reason", ""),
                "due_at": row.get("due_at"),
            }
            items.append(json_item(row["id"], "待跟进" if kind != "knowledge_gap" else "知识缺口", data))
    return ContextLayer("L3_VOLATILE", tuple(items))


def build_layers(
    snapshot: SourceSnapshot, system: str, clock: Clock, policy: BudgetPolicy
) -> tuple[list[ContextLayer], dict[str, dict[str, str | int]]]:
    aliases = AliasBook()
    layers = [
        ContextLayer("L0", (ContextItem("system", (ChatMessage("system", system),), True),)),
        fact_layer(snapshot, aliases),
        stable_layer(snapshot, aliases),
        history_layer(snapshot, aliases, policy),
        retrieval_layer(snapshot, aliases, policy),
        volatile_layer(snapshot, aliases),
    ]
    previous = next((row for row in reversed(snapshot.history) if row.get("role") == "user"), None)
    upcoming = [dict(row, id=aliases.add("f", "fact", row)) for row in snapshot.facts]
    upcoming.extend(
        dict(row, id=aliases.add("e", kind, row))
        for kind in ("followup", "reminder")
        for row in snapshot.extra_entities.get(kind, ())
    )
    now = render_now_block(snapshot.settings, clock, previous, upcoming)
    upcoming_ids = tuple(row["id"] for row in snapshot.facts)
    upcoming_ids += tuple(
        row["id"] for kind in ("followup", "reminder") for row in snapshot.extra_entities.get(kind, ())
    )
    layers.extend(
        [
            ContextLayer(
                "L1",
                (
                    ContextItem(
                        "now",
                        (ChatMessage("system", now),),
                        True,
                        source_ids=upcoming_ids,
                    ),
                ),
            ),
            current_layer(snapshot, aliases),
        ]
    )
    return layers, aliases.values
