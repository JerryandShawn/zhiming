"""A lexical notice is derived from native P8 proof without blocking publication."""

import json
from copy import deepcopy

import pytest

from mingjing_core.agent.loop_codec import extend_aliases, verified_versions
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.p8_boundary_review import (
    WARNING,
    boundary_warning,
    native_guidance,
    with_boundary_warning,
)
from mingjing_core.skills.boundary_messages import PILLARS
from mingjing_core.validation.structural import check_structure

from . import test_p8_boundary_delivery_pg as delivery
from . import test_p8_boundary_guidance_pg as guidance_tests
from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare


@pytest.fixture(name="repo")
def repository(p2_repo, monkeypatch):
    return delivery.repository.__wrapped__(p2_repo, monkeypatch)


class NoticePort(delivery.BoundaryPort):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def stream(self, messages, **kwargs):
        if len(self.requests) == 1:
            tool = next(row for row in reversed(messages) if row.role == "tool")
            self.guidance = json.loads(tool.content)["data"]["boundary_guidance"]
            item = self.guidance[0]
            label = PILLARS[item["affected_pillars"][0]]
            citation = f"〔{item['evidence_aliases'][0]}〕"
            text = f"{label}记录用于这次核对{citation}。"
            if self.mode == "notice":
                text += "存在交界，保留不同口径。"
            elif self.mode == "no_pillar":
                text = f"这里只核对资料{citation}。"
            elif self.mode == "no_citation":
                text = f"这里只提{label}这个名称。"
            elif self.mode == "full":
                text = item["text"]
            self.responses[1] = answer(text)
        yield from ScriptedPort.stream(self, messages, **kwargs)


@pytest.mark.parametrize("mode", ["missing", "notice", "no_pillar", "no_citation", "full"])
def test_actual_finalizer_records_only_nonblocking_body_free_warning(repo, mode):
    delivery.initialize(repo)
    run, registry, frozen = prepare(repo, "核对合成八字的时柱依据")
    port = NoticePort(mode)
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed", outcome.stop_reason
    guidance = native_guidance(repo, run, outcome.alias_map)
    assert guidance
    assert boundary_warning(repo, run, check_structure(outcome.text, outcome.alias_map), outcome.alias_map) == (
        mode == "missing"
    )
    result = AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    assert result["text"] == outcome.text
    assert result["review"] == {"state": "skipped", "reasons": [WARNING] if mode == "missing" else []}
    assert repo.fetch_run("alice", run["id"])["status"] == "succeeded"
    assert result["usage"]["model_steps"] == 2  # Original chart request and answer, no critic or extra step.


def test_native_warning_does_not_trust_pending_old_epoch_or_alias_identity(repo):
    h, args, ctx, step = guidance_tests.registered(repo)
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok
    assert native_guidance(repo, h.run, {}) == []
    h.journal.complete(step, result.model_dump())
    _, records = verified_versions(h.service, h.run, "chart_compute", result)
    aliases = {}
    extend_aliases(aliases, records)
    assert native_guidance(repo, h.run, aliases)
    assert native_guidance(repo, dict(h.run, retry_epoch=h.run["retry_epoch"] + 1), aliases) == []
    forged = deepcopy(aliases)
    for value in forged.values():
        value["native_id"] = "untrusted-native-id"
    assert native_guidance(repo, h.run, forged) == []
    h.finish()


def test_existing_review_state_and_reasons_are_not_overwritten(repo):
    h, args, ctx, step = guidance_tests.registered(repo)
    result = h.registry.execute("chart_compute", args, ctx)
    h.journal.complete(step, result.model_dump())
    _, records = verified_versions(h.service, h.run, "chart_compute", result)
    aliases = {}
    extend_aliases(aliases, records)
    item = native_guidance(repo, h.run, aliases)[0]
    text = f"{PILLARS[item['affected_pillars'][0]]}记录〔{item['evidence_aliases'][0]}〕。"
    checked = check_structure(text, aliases)
    # A valid public envelope projection is used only to exercise the pure merge;
    # Finalizer tests above use the real publication path and critic guards remain unchanged.
    from mingjing_core.agent.envelope import build_envelope

    envelope = build_envelope(h.run, checked, message_id="synthetic-warning-projection")
    envelope["review"] = {"state": "revised", "reasons": [{"code": "tone", "severity": 3}], "revision_id": "rev-1"}
    notice = boundary_warning(repo, h.run, checked, aliases)
    assert notice
    merged = with_boundary_warning(envelope, notice)
    assert merged["review"] == dict(envelope["review"], reasons=[{"code": "tone", "severity": 3}, WARNING])
    assert len(envelope["review"]["reasons"]) == 1
    assert with_boundary_warning(merged, notice) == merged
    h.finish()
