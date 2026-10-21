"""Unconnected projection experiment: unchanged oracle versus a conservative candidate, in this process only."""

import argparse
import hashlib
import importlib
import json
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.reflection_projection_exp import project_json  # noqa: E402
from mingjing_core.application.reflection_v3 import (  # noqa: E402
    plan_reflection_work,
    render_about_me,
    schedule_reflection,
)
from mingjing_core.application.reflection_v3.validation import (  # noqa: E402
    ReflectionError,
    dataclass_json,
    digest,
)
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.benchmark_reflection_v3 import (  # noqa: E402
    FIXTURE,
    SCOPE,
    arguments,
    full_workload,
    invalidation_workload,
)
from tools.mod_week.performance import measure, write_report  # noqa: E402

MODULES = tuple(
    importlib.import_module("mingjing_core.application.reflection_v3." + name)
    for name in ("validation", "intent_guard", "summaries", "work")
)
ORACLE = dataclass_json


def blocked_network(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("projection_experiment_network_disabled")


def isolate_process() -> None:
    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        os.environ[name] = ""
    os.environ["LANGCHAIN_TRACING_V2"] = os.environ["LANGSMITH_TRACING"] = "false"
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        setattr(socket, name, blocked_network)
    try:
        socket.getaddrinfo("synthetic.invalid", 443)
    except RuntimeError as error:
        assert str(error) == "projection_experiment_network_disabled"
    else:
        raise ValueError("projection_experiment_network_guard_missing")


@contextmanager
def candidate_hook() -> Iterator[None]:
    originals = tuple(module.dataclass_json for module in MODULES)
    if any(value is not ORACLE for value in originals):
        raise ValueError("projection_experiment_aliases_not_pristine")
    try:
        for module in MODULES:
            module.dataclass_json = project_json
        yield
    finally:
        for module, original in zip(MODULES, originals, strict=True):
            module.dataclass_json = original
        if any(module.dataclass_json is not original for module, original in zip(MODULES, originals, strict=True)):
            raise ValueError("projection_experiment_alias_restore_failed")


def semantic_capture(fixture: bytes) -> tuple[Any, ...]:
    values, document, incoming = arguments(fixture)
    decision = schedule_reflection(**values)
    work = plan_reflection_work(
        decision.intent, **values, profile=document, current_profile_revision=5, extracted_candidates=(incoming,)
    )
    view = render_about_me(
        document, snapshot=values["snapshot"], scope=SCOPE, clock=values["clock"], current_profile_revision=5
    )
    missing = dict(values, permit=None)
    blocked = schedule_reflection(**missing)
    thread_hidden = schedule_reflection(**dict(values, thread=replace(values["thread"], incognito=True)))
    first_source = values["snapshot"].sources[0]
    revoked = replace(
        values["snapshot"], sources=(replace(first_source, revoked=True), *values["snapshot"].sources[1:])
    )
    stale = plan_reflection_work(decision.intent, **dict(values, snapshot=revoked))
    foreign = replace(first_source, owner_id="synthetic-foreign-owner")
    mismatched = replace(values["snapshot"], sources=(foreign, *values["snapshot"].sources[1:]))
    try:
        schedule_reflection(**dict(values, snapshot=mismatched))
    except ReflectionError as error:
        foreign_reason = error.reason_code
    else:
        raise ValueError("projection_experiment_scope_guard_missing")
    assert blocked.disposition == thread_hidden.disposition == "blocked" and stale.status == "blocked"
    return decision, work, view, blocked, thread_hidden, stale, foreign_reason


def corpus(fixture: bytes) -> tuple[Any, ...]:
    decision, work, *_ = semantic_capture(fixture)
    return work, work.rolling_summary.excerpts, decision.intent.source_manifest, work.date_repairs


def local_projection(values: tuple[Any, ...], *, candidate: bool) -> int:
    projector = project_json if candidate else ORACLE
    for _ in range(100):
        for value in values:
            assert len(digest(projector(value))) == 64
    return 400


def hooked_workload(fixture: bytes, *, invalidation: bool) -> int:
    operation = invalidation_workload if invalidation else full_workload
    with candidate_hook():
        return operation(fixture)


def assert_parity(fixture: bytes, values: tuple[Any, ...]) -> str:
    # The old recursive function reads validation.dataclass_json dynamically; compare outside the hook.
    for value in values:
        assert ORACLE(value) == project_json(value)
        assert digest(ORACLE(value)) == digest(project_json(value))
    baseline = semantic_capture(fixture)
    with candidate_hook():
        experimental = semantic_capture(fixture)
    assert ORACLE(baseline) == ORACLE(experimental)
    fingerprint = digest(ORACLE(baseline))
    assert fingerprint == digest(ORACLE(experimental))
    try:
        with candidate_hook():
            raise RuntimeError("synthetic_hook_exit")
    except RuntimeError as error:
        assert str(error) == "synthetic_hook_exit"
    assert all(module.dataclass_json is ORACLE for module in MODULES)
    return fingerprint


def source_paths() -> list[Path]:
    paths = list((ROOT / "mingjing_core").rglob("*.py"))
    return sorted(
        paths
        + [
            Path(__file__),
            FIXTURE,
            ROOT / "tools/mod_week/benchmark_reflection_v3.py",
            ROOT / "tools/mod_week/performance.py",
        ]
    )


def measured_cases(fixture: bytes, values: tuple[Any, ...]) -> list[dict[str, Any]]:
    operations = (
        ("oracle_projection_and_digest_400", lambda: local_projection(values, candidate=False)),
        ("candidate_projection_and_digest_400", lambda: local_projection(values, candidate=True)),
        ("oracle_full_enqueue_work_aboutme_100", lambda: full_workload(fixture)),
        ("candidate_full_enqueue_work_aboutme_100", lambda: hooked_workload(fixture, invalidation=False)),
        ("oracle_revoked_epoch_invalidation_1000", lambda: invalidation_workload(fixture)),
        ("candidate_revoked_epoch_invalidation_1000", lambda: hooked_workload(fixture, invalidation=True)),
    )
    results = []
    for name, operation in operations:
        print("starting", name, flush=True)
        results.append(measure(name, operation))
        print("completed", name, results[-1]["median_seconds"], flush=True)
    return results


def describe(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for baseline, candidate in zip(cases[::2], cases[1::2], strict=True):
        rows.append(
            {
                "oracle": baseline["name"],
                "candidate": candidate["name"],
                "candidate_over_oracle_wall_ratio": candidate["median_seconds"] / baseline["median_seconds"],
                "candidate_over_oracle_allocation_peak_ratio": candidate["separate_tracemalloc_peak_bytes"]
                / baseline["separate_tracemalloc_peak_bytes"],
            }
        )
    return rows


def main() -> None:
    isolate_process()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    if output.resolve().exists():
        raise ValueError("projection_experiment_output_must_be_new")
    fixture, paths = FIXTURE.read_bytes(), source_paths()
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    values = corpus(fixture)
    parity = assert_parity(fixture, values)
    cases = measured_cases(fixture, values)
    assert parity == assert_parity(fixture, values)
    assert paths == source_paths()
    assert before == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    report = write_report(output, cases, paths, clock=SystemClock())
    report.update(
        {
            "experiment": "RPF01_unconnected_projection",
            "semantic_capture_sha256": parity,
            "oracle_aliases_restored": all(module.dataclass_json is ORACLE for module in MODULES),
            "source_sha256_before_after_equal": True,
            "source_path_set_before_after_equal": True,
            "core_python_sources": len(list((ROOT / "mingjing_core").rglob("*.py"))),
            "process_id": os.getpid(),
            "process_isolation": "Keys blank, tracing false, socket/DNS entry points blocked before workload",
            "comparisons": describe(cases),
            "scope": "Four reflection aliases in this independent process only; no Q2/U4 monkeypatch",
            "timed_full_work": "Frozen benchmark: fixture decode, input construction, all guards and assertions",
            "timed_local_work": "400 projections plus old digest; corpus prepared outside, not full-chain performance",
            "excluded": "Imports, fixture byte read, source hashes, semantic parity proof, evidence writes",
            "compatibility": "22 exact types; string keys; depth<=64; unknown classes and subclasses rejected",
        }
    )
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
