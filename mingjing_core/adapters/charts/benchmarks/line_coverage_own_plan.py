"""AST-only candidate plans: no importing, pytest collection, or execution."""

from __future__ import annotations

import ast
from pathlib import Path

from .line_coverage_manifest import digest, normalized
from .line_coverage_own_inventory import validate_own_inventory
from .line_coverage_own_sources import raw_sources

CORE_FILE = "tests/v4/test_p8_e2_night28_controls.py"
CHARTS_FILE = "tests/test_p8_daily_transit_native.py"
CANDIDATES = {
    CORE_FILE
    + "::test_matching_is_reproducible_and_independent_of_input_order": "core",
    CORE_FILE
    + "::test_no_chart_only_has_original_question_and_permuted_options": "core",
    CORE_FILE + "::test_empty_batch_is_available_without_a_fabricated_score": "core",
    CHARTS_FILE
    + "::NativeDailyTransit::test_daily_day_pillars_advance_one_sexagenary_step": "charts",
}
VERSION = "p8-history-static-sampling-plan-v2"


def _selected(runtime: str, node_ids: tuple[str, ...]) -> list[str]:
    if runtime not in ("core", "charts"):
        raise ValueError("own_plan_runtime_invalid")
    if not isinstance(node_ids, (tuple, list)) or not node_ids:
        raise ValueError("own_plan_nodes_required")
    if any(not isinstance(node, str) for node in node_ids):
        raise ValueError("own_plan_node_invalid")
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("own_plan_duplicate_node")
    if any(CANDIDATES.get(node) != runtime for node in node_ids):
        raise ValueError("own_plan_exact_candidate_required")
    return sorted(node_ids)


def _one(
    body: list[ast.stmt], kind: type[ast.ClassDef] | type[ast.FunctionDef], name: str
) -> ast.ClassDef | ast.FunctionDef:
    found = [item for item in body if isinstance(item, kind) and item.name == name]
    if len(found) != 1:
        raise ValueError("own_plan_ast_target_not_unique")
    return found[0]


def _span(node: ast.ClassDef | ast.FunctionDef, name: str) -> dict:
    return {"name": name, "start_line": node.lineno, "end_line": node.end_lineno}


def _shape(node: ast.FunctionDef, runtime: str) -> None:
    args = node.args
    expected = [] if runtime == "core" else ["self"]
    if (
        [item.arg for item in args.args] != expected
        or args.posonlyargs
        or args.kwonlyargs
        or args.vararg is not None
        or args.kwarg is not None
        or args.defaults
        or args.kw_defaults
        or node.decorator_list
    ):
        raise ValueError("own_plan_fixture_or_parameter_review_required")


def _hooks(module: ast.Module, parent: ast.ClassDef | None) -> list[dict]:
    result = []
    for item in module.body:
        if isinstance(item, ast.FunctionDef) and item.name in (
            "setUpModule",
            "tearDownModule",
        ):
            result.append(_span(item, item.name))
    if parent is not None:
        for item in parent.body:
            if isinstance(item, ast.FunctionDef) and item.name in (
                "setUpClass",
                "tearDownClass",
                "setUp",
                "tearDown",
            ):
                result.append(_span(item, parent.name + "." + item.name))
    return result


def _native_parent(module: ast.Module, name: str) -> ast.ClassDef:
    parent = _one(module.body, ast.ClassDef, name)
    if (
        parent.decorator_list
        or parent.keywords
        or len(parent.bases) != 1
        or ast.dump(parent.bases[0])
        != ast.dump(ast.parse("unittest.TestCase", mode="eval").body)
    ):
        raise ValueError("own_plan_unittest_base_review_required")
    return parent


def _entry(root: Path, inventory: dict, node_id: str, runtime: str) -> dict:
    parts = node_id.split("::")
    file = next((row for row in inventory["files"] if row["path"] == parts[0]), None)
    if file is None:
        raise ValueError("own_plan_candidate_not_in_owned_inventory")
    raw = raw_sources(root, {parts[0]: file["git_blob_id"]})[parts[0]]
    try:
        module = ast.parse(normalized(raw), filename=parts[0])
    except (SyntaxError, ValueError, UnicodeError):
        raise ValueError("own_plan_source_parse_failed") from None
    parent = _native_parent(module, parts[1]) if runtime == "charts" else None
    function = _one(parent.body if parent else module.body, ast.FunctionDef, parts[-1])
    _shape(function, runtime)
    return {
        "node_id": node_id,
        "runtime": runtime,
        "framework": "pytest" if runtime == "core" else "stdlib_unittest",
        "path": parts[0],
        "lf_sha256": file["lf_sha256"],
        "target": _span(function, function.name),
        "lifecycle_hooks": _hooks(module, parent),
        "selection_review": "fixed-candidate-only-not-authorization-to-execute",
        "hidden_import_or_helper_effects_proven_safe": False,
    }


def build_static_plan(
    root: Path, inventory: dict, *, runtime: str, node_ids: tuple[str, ...]
) -> dict:
    selected = _selected(runtime, node_ids)
    validate_own_inventory(root, inventory)
    config = next(
        (
            row
            for row in inventory["static_source_guards"]
            if row["path"] == "pytest.ini"
        ),
        None,
    )
    if config is None:
        raise ValueError("own_plan_pinned_configuration_required")
    result = {
        "version": VERSION,
        "commit": inventory["commit"],
        "inventory_sha256": inventory["inventory_sha256"],
        "inventory_complete_for_p8_history": inventory[
            "inventory_complete_for_p8_history"
        ],
        "coverage_collected": False,
        "execution_approved": False,
        "runtime": runtime,
        "entries": [_entry(root, inventory, node, runtime) for node in selected],
        "pinned_configuration": [config],
        "denominator_files": len(inventory["files"]),
        "unselected_files_still_in_denominator": True,
        "required_before_execution": [
            "Explicit root approval of B1/B2 and each exact node, dependency, fixture, and process budget.",
            "Interpreter/dependency fingerprints; real HEAD and source/config pre/post verification.",
            "Clear credentials; deny network/model/child processes; discard all captured test text.",
            "Fresh private temporary directories and exclusive new evidence paths.",
            "Small baseline and trace overhead trial before any expanded run; no automatic sampling.",
        ],
        "limits": [
            "AST parsing does not execute or collect tests and cannot prove indirect effects absent.",
            "Native lifecycle hooks are listed, not bypassed or executed; child-spawning suites remain unapproved.",
            "This artifact is a static candidate plan, not a coverage receipt or permission token.",
        ],
    }
    result["plan_sha256"] = digest(result)
    return result


def validate_static_plan(root: Path, inventory: dict, plan: dict) -> None:
    if not isinstance(plan, dict) or plan.get("version") != VERSION:
        raise ValueError("own_plan_shape_invalid")
    if (
        plan.get("execution_approved") is not False
        or plan.get("coverage_collected") is not False
    ):
        raise ValueError("own_plan_static_state_invalid")
    entries = plan.get("entries")
    if not isinstance(entries, list) or any(
        not isinstance(row, dict) for row in entries
    ):
        raise ValueError("own_plan_entries_invalid")
    payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan.get("plan_sha256") != digest(payload):
        raise ValueError("own_plan_integrity_invalid")
    rebuilt = build_static_plan(
        root,
        inventory,
        runtime=plan.get("runtime"),
        node_ids=tuple(row.get("node_id") for row in entries),
    )
    if plan != rebuilt:
        raise ValueError("own_plan_pinned_source_mismatch")
