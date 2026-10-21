"""Finite post-import origin diagnostics; no third-party code is imported by these models."""

from __future__ import annotations

import sys
from dataclasses import replace
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

import pytest
from b1_runtime_import_origins_support import module_at, modules_at

from tools import b1_linux_application_drill_origins as origins
from tools import b1_linux_application_drill_runtime as runtime
from tools.b1_linux_application_drill_contracts import ApplicationBlocked, ApplicationRequest


@pytest.fixture
def model(tmp_path, monkeypatch):
    prefix = tmp_path / "actual-running-interpreter"
    site = prefix / "Lib/site-packages"
    site.mkdir(parents=True)
    modules = modules_at(site)
    monkeypatch.setattr(origins.sys, "prefix", str(prefix))
    monkeypatch.setattr(origins.sysconfig, "get_path", lambda name: str(site))
    for name in origins.NAMESPACES:
        monkeypatch.setitem(sys.modules, name, modules[name])
    request = ApplicationRequest(
        "b1-import-model-only", "runtime", tmp_path / "unrelated-candidate", Path(sys.executable), True
    )
    return request, site, modules


def verify(model):
    request, _, modules = model
    return origins.verify_third_party_origins(request, modules)


def test_local_temporary_model_accepts_realistic_namespace_without_attesting_linux(model):
    assert verify(model) is None
    assert model[0].local_drill is True
    assert model[2]["langgraph"].__file__ is None


def test_namespace_can_have_multiple_search_locations_when_all_are_inside_actual_site(model):
    _, site, modules = model
    extra = site / "second-namespace-location"
    extra.mkdir()
    namespace = modules["langgraph"]
    namespace.__path__.append(str(extra))
    namespace.__spec__.submodule_search_locations.append(str(extra))
    assert verify(model) is None


def test_namespace_ancestor_may_become_a_regular_package(model, monkeypatch):
    _, site, modules = model
    regular = module_at("langgraph", site)
    monkeypatch.setitem(sys.modules, "langgraph", regular)
    assert verify(model) is None


@pytest.mark.parametrize("name", origins.LEAVES)
def test_explicit_leaf_cannot_succeed_with_none_file_even_with_valid_namespace_paths(model, name):
    value = model[2][name]
    value.__file__ = None
    value.__spec__.origin = None
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_NAMESPACE"):
        verify(model)


@pytest.mark.parametrize("change", ["spec_missing", "wrong_name", "empty", "none", "path_missing", "disagree"])
def test_namespace_requires_actual_coherent_nonempty_spec_and_search_paths(model, change):
    _, site, modules = model
    value = modules["langgraph"]
    if change == "spec_missing":
        value.__spec__ = None
    elif change == "wrong_name":
        value.__spec__.name = "other_namespace"
    elif change == "empty":
        value.__spec__.submodule_search_locations = []
    elif change == "none":
        value.__spec__.submodule_search_locations = None
    elif change == "path_missing":
        del value.__path__
    else:
        another = site / "other-location"
        another.mkdir()
        value.__path__ = [str(another)]
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_(IMPORT_SPEC|PACKAGE_PATH)"):
        verify(model)


@pytest.mark.parametrize("view", ["spec", "module", "both"])
def test_outside_namespace_path_cannot_hide_behind_one_correct_view(model, tmp_path, view):
    outside = tmp_path / "private-foreign-namespace"
    outside.mkdir()
    value = model[2]["langgraph"]
    if view in {"spec", "both"}:
        value.__spec__.submodule_search_locations.append(str(outside))
    if view in {"module", "both"}:
        value.__path__.append(str(outside))
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_OUTSIDE_VENV") as error:
        verify(model)
    assert str(outside) not in str(error.value)


def test_regular_package_search_paths_must_also_stay_inside(model, tmp_path):
    outside = tmp_path / "foreign-package-directory"
    outside.mkdir()
    value = model[2]["psycopg"]
    value.__path__.append(str(outside))
    value.__spec__.submodule_search_locations.append(str(outside))
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_OUTSIDE_VENV"):
        verify(model)


@pytest.mark.parametrize("change", ["outside", "prefix_collision", "relative", "missing", "spec_mismatch", "spec_none"])
def test_leaf_file_and_spec_cannot_point_outside_or_disagree(model, tmp_path, change):
    _, site, modules = model
    value = modules["pydantic"]
    if change == "outside":
        outside = tmp_path / "foreign.py"
        outside.write_text("# never imported", encoding="utf-8")
        value.__file__ = value.__spec__.origin = str(outside)
    elif change == "prefix_collision":
        outside = site.with_name("site-packages-foreign") / "foreign.py"
        outside.parent.mkdir()
        outside.write_text("# never imported", encoding="utf-8")
        value.__file__ = value.__spec__.origin = str(outside)
    elif change == "relative":
        value.__file__ = value.__spec__.origin = "relative/module.py"
    elif change == "missing":
        value.__file__ = value.__spec__.origin = str(site / "does-not-exist.py")
    elif change == "spec_mismatch":
        value.__spec__.origin = modules["psycopg"].__file__
    else:
        value.__spec__ = None
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_(OUTSIDE_VENV|IMPORT_ORIGIN|IMPORT_SPEC)"):
        verify(model)


def test_path_location_iteration_is_bounded_before_allocating_unbounded_model_input(model):
    value = model[2]["langgraph"]
    yielded = []

    def unbounded():
        while True:
            yielded.append(True)
            yield value.__path__[0]

    value.__spec__.submodule_search_locations = unbounded()
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_PATH_LIMIT"):
        verify(model)
    assert len(yielded) == origins.MAX_LOCATIONS + 1


@pytest.mark.parametrize("change", ["prefix", "sysconfig"])
def test_formal_root_is_fixed_even_if_interpreter_configuration_disagrees(model, monkeypatch, tmp_path, change):
    request, site, modules = model
    prefix = Path(origins.sys.prefix)
    monkeypatch.setattr(origins, "FORMAL_CORE", prefix)
    monkeypatch.setattr(origins, "FORMAL_SITE", site)
    assert origins.verify_third_party_origins(replace(request, local_drill=False), modules) is None
    outside = tmp_path / "different-interpreter"
    outside.mkdir()
    if change == "prefix":
        monkeypatch.setattr(origins.sys, "prefix", str(outside))
    else:
        monkeypatch.setattr(origins.sysconfig, "get_path", lambda name: str(outside))
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_ROOTS"):
        origins.verify_third_party_origins(replace(request, local_drill=False), modules)


def test_local_roots_cannot_be_redirected_by_caller_candidate_fields(model, tmp_path):
    request, site, modules = model
    unrelated = tmp_path / "caller-selected"
    unrelated.mkdir()
    request = replace(request, candidate_source=unrelated, candidate_python=unrelated / "python")
    assert origins.verify_third_party_origins(request, modules) is None
    modules["psycopg"] = module_at("psycopg", unrelated)
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_OUTSIDE_VENV"):
        origins.verify_third_party_origins(request, modules)
    assert site.is_dir()


def test_local_sysconfig_cannot_borrow_system_site_outside_current_prefix(model, tmp_path, monkeypatch):
    system_site = tmp_path / "system-site-packages"
    system_site.mkdir()
    monkeypatch.setattr(origins.sysconfig, "get_path", lambda name: str(system_site))
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_ROOTS"):
        verify(model)


def test_missing_explicit_namespace_never_succeeds_as_an_empty_collection(model, monkeypatch):
    monkeypatch.delitem(sys.modules, "langgraph.checkpoint")
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_NAMESPACE"):
        verify(model)


def test_core_external_source_keeps_original_refusal_before_third_party_diagnostics(model, monkeypatch):
    request, _, _ = model
    value = ModuleType("synthetic-external")
    value.__file__ = __file__
    monkeypatch.setattr(runtime.importlib, "import_module", lambda name: value)
    monkeypatch.setattr(
        runtime, "verify_third_party_origins", lambda *args: pytest.fail("Core refusal must be first"), raising=False
    )
    with pytest.raises(ApplicationBlocked, match="APPLICATION_IMPORT_OUTSIDE_CANDIDATE"):
        runtime.critical_imports(request)


def test_nonpackage_leaf_with_file_can_have_no_search_locations(model):
    value = model[2]["pydantic"]
    value.__spec__ = ModuleSpec("pydantic", loader=None, origin=value.__file__)
    del value.__path__
    assert verify(model) is None


def complete_core_modules(request, modules):
    for name in (
        "mingjing_core.repositories.postgres",
        "mingjing_core.application.memory",
        "mingjing_core.runtime",
    ):
        modules[name] = module_at(name, request.candidate_source)


def test_critical_imports_refuses_external_dependency_after_valid_core_sources(model, tmp_path, monkeypatch):
    request, _, modules = model
    complete_core_modules(request, modules)
    outside = tmp_path / "external-dependency"
    modules["pydantic"] = module_at("pydantic", outside)
    monkeypatch.setattr(runtime.importlib, "import_module", lambda name: modules[name])
    with pytest.raises(ApplicationBlocked, match="APPLICATION_DEPENDENCY_OUTSIDE_VENV"):
        runtime.critical_imports(request)


def test_critical_imports_returns_exact_original_seven_names_with_valid_namespace(model, monkeypatch):
    request, _, modules = model
    complete_core_modules(request, modules)
    monkeypatch.setattr(runtime.importlib, "import_module", lambda name: modules[name])
    assert runtime.critical_imports(request) == [
        "psycopg",
        "langgraph.graph",
        "langgraph.checkpoint.postgres",
        "pydantic",
        "mingjing_core.repositories.postgres",
        "mingjing_core.application.memory",
        "mingjing_core.runtime",
    ]
