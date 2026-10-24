"""Create declared privacy fixtures in actual native stores before withdrawal."""

from __future__ import annotations

from typing import Any

from tools.eval.targets.v3_seed import V3Seeder
from tools.eval.targets.v4_privacy_seed_native import historical_run, seed_native_layer

PRIVACY_CASES = {"F01", "F02", "F03"}


class V4PrivacySeeder(V3Seeder):
    def seed(self, seed: dict[str, Any]) -> None:
        self.privacy_layers: list[dict[str, Any]] = []
        self.privacy_aliases: dict[str, str] = {}
        super().seed(seed)
        if self.scenario not in PRIVACY_CASES:
            return
        self.privacy_aliases = {self.ids[row["id"]]: row["id"] for row in seed.get("thread", [])}
        users = [self.ids[row["id"]] for row in seed.get("thread", []) if row.get("role", "user") == "user"]
        repo = self.service.repo
        for fixture in seed.get("facts", []):
            fact = repo.get(self.owner, "fact", self.ids[fixture["id"]])
            changes = {name: fixture[name] for name in ("sensitivity", "event_at") if fixture.get(name)}
            if changes:
                repo.update(self.owner, "fact", fact["id"], changes, expected_revision=fact["revision"])
        for entity in seed.get("entities", []):
            if entity["kind"] != "case":
                self.seed_layer(entity, users)
        self.assistant_dependencies(seed)

    def layer_sources(self, declared: dict[str, Any], users: list[str]) -> tuple[list[str], str | None]:
        fact_id = self.ids.get(declared.get("source_fact_id"))
        if fact_id:
            fact = self.service.repo.get(self.owner, "fact", fact_id)
            return [ref["message_id"] for ref in fact["source_refs"]], fact_id
        if declared.get("source_ids"):
            return [self.ids[value] for value in declared["source_ids"]], None
        if len(users) == 1:
            return users, None
        raise ValueError("Declared privacy fixture has no unique actual source")

    def seed_layer(self, entity: dict[str, Any], users: list[str]) -> None:
        declared = entity.get("data", {})
        sources, fact_id = self.layer_sources(declared, users)
        refs = [self.source_ref(value) for value in sources]
        kind, ident = entity["kind"], entity["id"]
        record = {"kind": kind, "id": ident, "sources": sources, "fact_id": fact_id}
        if kind == "fact":
            source = self.service.repo.get(self.owner, "message", sources[0])
            self.seed_existing_fact(
                {
                    "id": ident,
                    "kind": "background",
                    "quote": source["content"],
                    "source_message_id": next(key for key, value in self.ids.items() if value == source["id"]),
                }
            )
            record.update(native_kind="fact", native_id=self.ids[ident])
        elif kind in {"search_hit", "embedding", "run_event", "run_step"}:
            seed_native_layer(self, record, refs)
        elif kind in {"followup", "profile_item", "note", "episode", "thread_summary", "proposal"}:
            native = "profile_doc" if kind == "profile_item" else kind
            common = dict(declared, source_ids=sources, source_refs=refs, used_fact_ids=[fact_id] if fact_id else [])
            row = self.service.repo.put(
                self.owner,
                native,
                ident,
                dict(common, status=entity.get("status", "active")),
                expected_revision=0,
                operation_id="seed-derived:" + ident,
            )
            self.ids[ident] = row["id"]
            record.update(native_kind=native, native_id=row["id"])
        else:
            raise ValueError("Unimplemented native privacy fixture kind: " + kind)
        self.privacy_layers.append(record)

    def assistant_dependencies(self, seed: dict[str, Any]) -> None:
        # Adjacent turns supply actual previous-user/fact dependencies.
        previous, repo = None, self.service.repo
        for message in seed.get("thread", []):
            if message.get("role", "user") == "user":
                previous = self.ids[message["id"]]
            elif message.get("role") == "assistant" and previous:
                row = repo.get(self.owner, "message", self.ids[message["id"]])
                facts = [
                    fact["id"]
                    for fact in repo.list(self.owner, "fact")
                    if any(ref["message_id"] == previous for ref in fact.get("source_refs", []))
                ]
                repo.update(
                    self.owner,
                    "message",
                    row["id"],
                    {
                        "run_id": historical_run(self, [previous], message["id"]),
                        "source_ids": [previous],
                        "source_refs": [self.source_ref(previous)],
                        "used_fact_ids": facts,
                    },
                    expected_revision=row["revision"],
                )

    def source_ref(self, ident: str) -> dict[str, Any]:
        source = self.service.repo.get(self.owner, "message", ident)
        return {
            "message_id": ident,
            "version": source["revision"],
            "start": 0,
            "end": len(source["content"]),
            "quote": source["content"],
        }
