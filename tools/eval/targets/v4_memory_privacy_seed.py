"""Declared synthetic derivations use native storage, never model-supplied DB mutations."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.memory.tokenize import tokenize
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.providers.scripted import ScriptedProvider


class MemoryPrivacySeeder:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.ids: dict[str, str] = {}
        self.source_ids: set[str] = set()
        self.embedding_targets: set[tuple[str, str]] = set()
        self.runtime_ids: list[str] = []
        self.setup_calls = 0
        self.query_tokens: tuple[str, ...] = ()
        self.query_ids: set[str] = set()
        self.baseline: dict[str, int] = {}

    def seed(self) -> None:
        fixtures = self.target.seed.get("entities", [])
        if not any(f["kind"] in {"profile_item", "run_step", "run_event", "search_hit", "embedding"} for f in fixtures):
            return
        for fixture in fixtures:
            if fixture["kind"] == "fact":
                self._fact(fixture)
        for fixture in fixtures:
            if fixture["kind"] in {"followup", "profile_item", "note", "episode", "thread_summary"}:
                self._derived(fixture)
            elif fixture["kind"] == "embedding":
                self._embedding(fixture)
        sources = [self.target.repo.get(self.target.owner, "message", ident) for ident in self.source_ids]
        self.query_tokens = tuple(dict.fromkeys(token for row in sources for token in tokenize(row.get("content", ""))))
        self.query_ids = self.source_ids | set(self.ids.values()) | set(self.target.seeder.ids.values())
        if any(f["kind"] in {"run_step", "run_event"} for f in fixtures):
            self._runtime()
        from .v4_memory_privacy_views import native_counts

        self.baseline = native_counts(self)
        required = {
            f["kind"]
            for f in fixtures
            if f["kind"] in {"embedding", "run_step", "run_event", "profile_item", "search_hit"}
        }
        if any(self.baseline.get(kind, 0) < 1 for kind in required):
            raise ValueError("Declared privacy layer was not actually present before withdrawal")

    def _fact(self, fixture: dict[str, Any]) -> None:
        target = self.target
        sources = fixture["data"].get("source_ids", [])
        if len(sources) != 1:
            raise ValueError("Synthetic derived fact needs one exact original source")
        source = target.service.memory.get_source(target.owner, target.seeder.ids[sources[0]])
        target.seeder.seed_existing_fact(
            {
                "id": fixture["id"],
                "source_message_id": sources[0],
                "quote": source["content"],
                "kind": "background",
                "status": fixture["status"],
            }
        )
        self.ids[fixture["id"]] = fixture["id"]
        self.source_ids.add(source["id"])

    def _links(self, fixture: dict[str, Any]) -> tuple[list[str], list[str]]:
        target, data = self.target, fixture["data"]
        facts = [target.seeder.ids[data["source_fact_id"]]] if data.get("source_fact_id") else []
        sources = [target.seeder.ids[label] for label in data.get("source_ids", [])]
        for ident in facts:
            fact = target.repo.get(target.owner, "fact", ident)
            sources += [ref["message_id"] for ref in fact.get("source_refs", [])]
        return list(dict.fromkeys(sources)), facts

    def _derived(self, fixture: dict[str, Any]) -> None:
        target = self.target
        kind = "profile_doc" if fixture["kind"] == "profile_item" else fixture["kind"]
        sources, facts = self._links(fixture)
        if not sources:
            raise ValueError("Declared derivation must have actual source lineage")
        self.source_ids.update(sources)
        refs = [
            {"message_id": ident, "version": target.repo.get(target.owner, "message", ident)["revision"]}
            for ident in sources
        ]
        target.repo.put(
            target.owner,
            kind,
            fixture["id"],
            {
                "content": "合成隐私传播初态",
                "inferred": True,
                "source_ids": sources,
                "source_refs": refs,
                "fact_ids": facts,
                "status": fixture["status"],
            },
            expected_revision=0,
        )
        self.ids[fixture["id"]] = fixture["id"]

    def _embedding(self, fixture: dict[str, Any]) -> None:
        target = self.target
        sources, facts = self._links(fixture)
        self.source_ids.update(sources)
        kind, ident = ("fact", facts[0]) if facts else ("message", sources[0])
        native = target.repo.get(target.owner, kind, ident)
        with target.repo.transaction(target.owner) as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(owner,kind,entity_id,chunk,model,vec,content_fp) VALUES(%s,%s,%s,0,%s,%s,%s)"
                ).format(target.repo.table("core_embeddings")),
                (
                    target.owner,
                    kind,
                    ident,
                    "synthetic-privacy-only",
                    [0.0, 1.0],
                    fingerprint(native.get("content", "")),
                ),
            )
        self.embedding_targets.add((kind, ident))
        self.ids[fixture["id"]] = ident

    def _runtime(self) -> None:
        target = self.target
        if len(self.source_ids) != 1:
            raise ValueError("Synthetic runtime derivation needs one source")
        source = target.service.memory.get_source(target.owner, next(iter(self.source_ids)))
        run = target.memory_actions._queue(source, "privacy-runtime")
        provider = ScriptedProvider([{"turn": 1, "model": [{"text": "合成初态回答，仅用于验证来源撤销传播。"}]}])
        target.port.start(provider, 1, {})
        before = target.port.calls
        target.runtime.execute(target.service, target.owner, run["id"], run["lease_token"], lambda event: None)
        self.setup_calls += target.port.calls - before
        self.runtime_ids.append(run["id"])
        target.run_ids.append(run["id"])

    def search(self) -> list[dict[str, Any]]:
        target = self.target
        rows = (
            target.repo.search(
                target.owner, "self", list(self.query_tokens), ["fact", "message", "note", "profile_doc"], limit=100
            )
            if self.query_tokens
            else []
        )
        return [row for row in rows if row["id"] in self.query_ids]


def prepare_memory(target: Any) -> None:
    from .v4_memory_actions import MemoryActionDriver
    from .v4_memory_withdraw_driver import MemoryWithdrawDriver

    target.memory_actions = MemoryActionDriver(target)
    target.memory_actions.seed()
    target.bindings.update(target.memory_actions.ids)
    target.privacy_seed = MemoryPrivacySeeder(target)
    target.privacy_seed.seed()
    target.bindings.update(target.seeder.ids)
    target.bindings.update(target.privacy_seed.ids)
    target.memory_withdrawals = MemoryWithdrawDriver(target)
