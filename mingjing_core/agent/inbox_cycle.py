"""Adopt inbox originals only at a model boundary, with persisted request proof."""

import copy
import json

from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_current_sources import current_source_ids
from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.domain.contracts import EvidenceError, ScopeError

from .inbox_crisis import refresh_crisis
from .loop_codec import extend_aliases


class InboxCycle:
    def __init__(self, repo):
        self.repo, self.pending = repo, ()

    def prepare(self, cycle, restored):
        run = cycle.run
        try:
            self.repo.get(run["owner"], "thread", run.get("thread_id") or "life:" + run["subject"])
        except ScopeError:
            return
        inbox = ThreadInbox(self.repo)
        if cycle.revising or cycle.crisis:
            inbox.defer(run)
            return
        iteration = cycle.usage["model_steps"] + 1
        claims = inbox.claim(run, phase="before_model", iteration=iteration)
        if restored is not None:
            cycle.messages = [
                copy.deepcopy(message)
                for layer in restored.budget.layers
                if layer.name == "CYCLE"
                for item in layer.items
                for message in item.messages
            ]
            with self.repo.transaction(run["owner"]) as connection:
                current = self.repo._run(self.repo._leased(connection, run["owner"], run["id"], run["lease_token"]))
                cycle.versions = reconcile_versions(self.repo, current, current["state_version"])
            cycle.current_sources = tuple(
                ident for ident in current_source_ids(self.repo, run) if "message:" + ident in restored.versions
            )
        self.pending = tuple(claim for claim in claims if self._admit(cycle, claim, restored))
        self._register_sources(cycle)
        refresh_crisis(cycle)

    def _admit(self, cycle, claim, restored):
        identifiers = tuple(key[8:] for key in claim.versions if key.startswith("message:"))
        if len(set((*cycle.current_sources, *identifiers))) > 100:
            return False
        if restored is not None:
            if any(restored.versions.get(key) != version for key, version in claim.versions.items()):
                return False
        else:
            metadata = {"supplemental_source_ids": list(identifiers), "source_segments": claim.source_segments}
            from mingjing_core.models.port import ChatMessage

            cycle.messages.append(ChatMessage("system", "运行中补充的程序来源标识：" + json.dumps(metadata)))
            cycle.messages.extend(copy.deepcopy(claim.user_messages))
            self._dependencies(cycle, claim.versions)
        cycle.current_sources = tuple(dict.fromkeys((*cycle.current_sources, *identifiers)))
        return True

    def _dependencies(self, cycle, additions):
        with self.repo.transaction(cycle.run["owner"]) as connection:
            row = self.repo._run(
                self.repo._leased(connection, cycle.run["owner"], cycle.run["id"], cycle.run["lease_token"])
            )
            versions = reconcile_versions(self.repo, row, row["state_version"])
            for key, version in additions.items():
                if key in versions and versions[key] != version:
                    raise EvidenceError("补充原话版本与当前依赖不一致")
                versions[key] = version
            if not self.repo.verify_versions(row["owner"], versions):
                raise EvidenceError("补充原话在发送前已经改变")
            self.repo.set_run_dependencies(row["owner"], row["id"], versions, row["lease_token"])
            cycle.versions = versions

    def _register_sources(self, cycle):
        # Restored requests authorize their own chronological source set, not future steps.
        records = []
        for ident in cycle.current_sources:
            row = self.repo.get(cycle.run["owner"], "message", ident)
            records.append(dict(kind="message", id=ident, revision=row["revision"]))
        extend_aliases(cycle.aliases, records)

    def completed(self, cycle, step):
        inbox = ThreadInbox(self.repo)
        for claim in self.pending:
            inbox.ack(cycle.run, claim, model_seq=step.seq)
        self.pending = ()
        if not set(cycle.current_sources).issubset(current_source_ids(self.repo, cycle.run)):
            raise EvidenceError("模型完成后的补充原话缺少真实采用证明")
        self._register_sources(cycle)
