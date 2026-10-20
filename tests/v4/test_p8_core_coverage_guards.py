"""B1 pure guard/lifecycle probes; no collector baseline or trace."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_boundary as boundary,
)
from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_fingerprint as fingerprint,
)
from mingjing_core.adapters.charts.benchmarks import line_coverage_core_git as metadata
from mingjing_core.adapters.charts.benchmarks.line_coverage_core_reports import Witness
from mingjing_core.adapters.charts.benchmarks.line_coverage_own_plan import CANDIDATES

NODE = next(k for k, v in CANDIDATES.items() if v == "core")


def gate():
    result = boundary.Gate(set(), boundary.ROOT / "private/tmp/b1-unit-unused")
    result.active = True
    return result


@pytest.mark.parametrize(
    "event,args,label",
    [
        ("open", (str(boundary.ROOT / "knowledge/private.json"), "r", 0), "file_read"),
        (
            "open",
            (str(boundary.ROOT / "private/tmp/unit.txt"), "w", os.O_WRONLY),
            "file_write_or_descriptor",
        ),
        ("open", (0, "r", 0), "file_write_or_descriptor"),
        ("socket.connect", (), "network"),
        ("socket.getaddrinfo", (), "network"),
        ("subprocess.Popen", (), "process"),
        ("os.system", (), "process"),
        ("sys.settrace", (), "trace_change"),
        ("sys.setprofile", (), "trace_change"),
        ("os.mkdir", (), "file_mutation"),
        ("os.remove", (), "file_mutation"),
        ("ctypes.dlopen", (), "unregistered_native_load"),
        ("ctypes.dlsym", (), "unregistered_native_load"),
        ("os.add_dll_directory", (), "unregistered_native_load"),
        (
            "import",
            ("unregistered", str(boundary.ROOT / "private/tmp/unregistered.pyd")),
            "import_source",
        ),
    ],
)
def test_audit_rejects_fixed_categories(event, args, label):
    value = gate()
    with pytest.raises(ValueError, match="b1_target_" + label):
        value.audit(event, args)
    assert value.blocked == {label: 1}


def test_bytecode_probe_is_source_fallback_not_loaded():
    value = gate()
    with pytest.raises(FileNotFoundError, match="b1_bytecode_probe"):
        value.audit("open", (str(boundary.ROOT / "private/tmp/missing.pyc"), "r", 0))
    assert value.skipped_bytecode_probes == 1 and not value.blocked


def test_only_exact_fingerprinted_source_read_allowed():
    path = (
        boundary.ROOT
        / "mingjing_core/adapters/charts/benchmarks/line_coverage_manifest.py"
    )
    value = boundary.Gate({str(path)}, path.parent)
    value.active = True
    value.audit("open", (str(path), "r", 0))
    value.audit("import", ("fingerprinted", str(path)))
    assert not value.blocked


@pytest.mark.parametrize(
    "method,label", [("process", "process"), ("thread", "thread"), ("input", "input")]
)
def test_direct_patch_denial_remains_recorded_after_caught_exception(method, label):
    value = gate()
    with pytest.raises(ValueError):
        getattr(value, method)("private content that must not be returned")
    assert value.blocked == {label: 1}


@pytest.mark.parametrize(
    "args,payload",
    [
        (("rev-parse", "HEAD"), b"x"),
        (("rev-parse", "--git-dir"), b"x"),
        (("rev-list", "--ancestry-path", "a" * 40 + ".." + "b" * 40, "--"), b"x"),
        (("rev-list", "--ancestry-path", "a" * 40 + ".." + "b" * 40), None),
        (("config", "--get", "user.name"), None),
        (("push",), None),
        (("cat-file", "--batch"), b"HEAD\n"),
        (("rev-parse", "a" * 40 + ":private.json"), None),
    ],
)
def test_git_denies_unapproved_command_or_payload(args, payload):
    with pytest.raises(ValueError, match="b1_git_arguments_not_allowlisted"):
        metadata.valid_arguments(args, payload)


@pytest.mark.parametrize(
    "args,payload",
    [
        (("rev-parse", "HEAD"), None),
        (("rev-parse", "--git-common-dir"), None),
        (("cat-file", "--batch"), b"a" * 40 + b"\n"),
        (("rev-list", "--ancestry-path", "a" * 40 + ".." + "b" * 40, "--"), None),
        (("rev-parse", "a" * 40 + ":requirements-core.lock"), None),
    ],
)
def test_git_fixed_metadata_shapes(args, payload):
    metadata.valid_arguments(args, payload)


def successful_witness():
    value = Witness(NODE)
    value.pytest_collection_modifyitems(
        None, None, [SimpleNamespace(nodeid=NODE, fixturenames=[])]
    )
    for phase in ("setup", "call", "teardown"):
        value.pytest_runtest_logreport(
            SimpleNamespace(nodeid=NODE, when=phase, outcome="passed")
        )
    value.pytest_sessionfinish(None, 0)
    return value


def test_witness_requires_real_three_phase_shape():
    assert successful_witness().successful(0)


@pytest.mark.parametrize(
    "mutation", ["skip", "xfail", "missing", "extra", "exit", "node", "fixture"]
)
def test_witness_rejects_lifecycle_shortcuts(mutation):
    value = successful_witness()
    if mutation == "skip":
        value.events[1]["outcome"] = "skipped"
    elif mutation == "xfail":
        value.events[1]["xfail"] = True
    elif mutation == "missing":
        value.events.pop()
    elif mutation == "extra":
        value.events.append(dict(value.events[1]))
    elif mutation == "exit":
        value.exit_code = 1
    elif mutation == "node":
        value.selected = [NODE + "_other"]
    else:
        with pytest.raises(ValueError):
            value.pytest_collection_modifyitems(
                None, None, [SimpleNamespace(nodeid=NODE, fixturenames=["tmp_path"])]
            )
    assert not value.successful(0)


def launch(monkeypatch, optimize=0):
    flags = {name: 0 for name in fingerprint.FLAGS}
    flags.update(
        {
            name: 1
            for name in (
                "dont_write_bytecode",
                "no_user_site",
                "no_site",
                "ignore_environment",
                "isolated",
                "hash_randomization",
                "safe_path",
            )
        }
    )
    flags["optimize"] = optimize
    monkeypatch.setattr(fingerprint.sys, "flags", SimpleNamespace(**flags))
    monkeypatch.setattr(fingerprint.sys, "pycache_prefix", "unit-cache")
    entry = (
        fingerprint.ROOT
        / "mingjing_core/adapters/charts/benchmarks/line_coverage_core_bootstrap.py"
    )
    monkeypatch.setattr(
        fingerprint.sys,
        "orig_argv",
        ["python", "-I", "-S", "-B", "-X", "pycache_prefix=unit-cache", str(entry)],
    )


@pytest.mark.parametrize("optimize", [1, 2])
def test_optimized_start_rejected_before_target(monkeypatch, optimize):
    launch(monkeypatch, optimize)
    with pytest.raises(ValueError, match="b1_noncanonical_launch_flags"):
        fingerprint.launch_metadata()


def test_launch_records_all_flags_without_arbitrary_xoption_text(monkeypatch):
    launch(monkeypatch)
    result = fingerprint.launch_metadata()
    assert set(result["flags"]) == set(fingerprint.FLAGS)
    assert result["xoptions"] == {"pycache_prefix": "fresh-private-cache"}


@pytest.mark.parametrize("optimize", [1, 2])
def test_bootstrap_also_rejects_optimized_launch(monkeypatch, optimize):
    from mingjing_core.adapters.charts.benchmarks import (
        line_coverage_core_bootstrap as bootstrap,
    )

    launch(monkeypatch, optimize)
    assert bootstrap.invalid_launch(
        fingerprint.ROOT, fingerprint.CORE, Path("unused-cache")
    )


def test_trace_lifecycle_gate_false_during_install_and_cleanup_with_fake_tracer(
    monkeypatch,
):
    from contextlib import nullcontext

    from mingjing_core.adapters.charts.benchmarks import line_coverage_core_run as run

    value = gate()
    value.active = False
    events = []

    class FakeTrace:
        def __init__(self, **kwargs):
            pass

        def runfunc(self, function, *args):
            events.append(("install", value.active))
            result = function(*args)
            events.append(("cleanup", value.active))
            return result

        def results(self):
            return SimpleNamespace(counts={})

    def fake_execute(*args):
        value.active = True
        try:
            events.append(("synthetic_body", value.active))
            return 0
        finally:
            value.active = False

    monkeypatch.setattr(run.trace, "Trace", FakeTrace)
    monkeypatch.setattr(run, "_execute", fake_execute)
    monkeypatch.setattr(run, "boundaries", lambda gate: nullcontext())
    result = run._trial(value, Witness(NODE), NODE, "trace", Path("unused-cache"))
    assert result[0:2] == (0, "completed")
    assert events == [("install", False), ("synthetic_body", True), ("cleanup", False)]


def test_caught_guard_denial_still_fails_receipt(monkeypatch):
    from mingjing_core.adapters.charts.benchmarks import line_coverage_core_run as run

    value = gate()
    witness = successful_witness()
    with pytest.raises(ValueError):
        value.process()
    inv = {"commit": "a" * 40, "inventory_sha256": "b" * 64, "files": []}
    result = run._receipt(
        inv,
        {"plan_sha256": "c" * 64},
        NODE,
        "trace",
        witness,
        (0, "completed", 0.01, {}),
        value,
        True,
    )
    assert result["status"] == "failed" and result["eligible_for_union"] is False
    assert result["blocked_attempts"] == {"process": 1}


def test_original_stream_buffers_flush_before_output_descriptors_restore(monkeypatch):
    import io

    events = []

    class Probe(io.StringIO):
        def flush(self):
            events.append("flush")

    probe = Probe()
    monkeypatch.setattr(boundary.sys, "__stdout__", probe)
    original_dup2 = boundary.os.dup2

    def track_dup2(source, destination):
        events.append(("dup2", destination))
        return original_dup2(source, destination)

    monkeypatch.setattr(boundary.os, "dup2", track_dup2)
    value = gate()
    value.active = False
    with boundary.boundaries(value):
        assert boundary.sys.__stdout__ is not probe
        boundary.sys.__stdout__.write("SYNTHETIC_PRIVATE_MARKER")
        probe.write("HELD_REFERENCE_SYNTHETIC")
    assert events[0] == "flush"
    assert events[-3:] == ["flush", ("dup2", 1), ("dup2", 2)]
    assert "SYNTHETIC_PRIVATE_MARKER" not in probe.getvalue()
