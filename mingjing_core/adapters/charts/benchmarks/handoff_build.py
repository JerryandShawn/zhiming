"""Build three read-only previews from the canonical, entirely synthetic 阿远."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

from ..p8_adapter import P8ChartAdapter
from ..p8_worker import source_hashes
from .handoff_boundaries import (
    add_boundary_views,
    boundary_binding,
    rule_evidence,
    rule_refs,
)
from .handoff_offline import offline_runtime
from .handoff_refs import alias, document, reference, resolve
from .handoff_schema import CONTRACT_VERSION, VIEW_KEYS, schema

BIRTH = {
    "date": "1994-03-12",
    "reported_time": "08:20",
    "gender": "男",
    "place": {"tz": "Asia/Shanghai", "lon": 104.07, "lat": 30.67},
    "clock_basis": "clock",
    "precision": "reported",
}
TARGET = "2026-10-19"


def _scope(system: str) -> dict:
    return {
        "owner_user_id": "synthetic-owner-ayuan",
        "subject_id": "synthetic-subject-ayuan",
        "revision": 1,
        "operation_id": f"synthetic-ayuan-{system}-20261019",
    }


def _base(system: str, scope: dict, physical: str) -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "draft_integration_contract",
        "mode": "scripted_synthetic_preview",
        "display_name": "阿远",
        "scope": scope,
        "request": {
            "system": system,
            "target_date": TARGET,
            "time_scale": "natal_with_explicit_target_layers",
            "birth": deepcopy(BIRTH),
            "physical_birth_at_utc": physical,
        },
        "documents": [],
        "view": {key: [] for key in VIEW_KEYS},
        "aliases": {"c": [], "r": []},
        "effects": {
            "model_calls": 0,
            "writes": 0,
            "alias_registry": "ephemeral_demo_only",
        },
        "warnings": [
            "完全合成的阿远，使用07号§0.4同一画像；不是用户出生资料。",
            "这是待主线接入的只读契约草稿；原生产物保留，演示别名仅本文件本轮有效。",
            "传统结构、候选与数值正确性不证明人生预测有效；未创建API、档案或持久化别名。",
        ],
    }


def _basis_views(preview: dict, doc: dict) -> None:
    system = preview["request"]["system"]
    view, raw = preview["view"], doc["payload"]
    view["time_basis"] = [reference(doc, "/time_basis")]
    for index, chart in enumerate(raw["charts"]):
        basis = chart["time_basis"]["basis"]
        role = {
            "primary": "primary",
            "comparison": "comparisons",
            "diagnostic": "diagnostics",
        }[chart["interpretation_role"]]
        prefix = f"/charts/{index}"
        path = prefix + ("/data" if system == "bazi" else "/ziwei_column")
        view[role].append(reference(doc, path))
        if basis != "true_solar":
            continue
        if system == "bazi":
            p8 = chart["data"]["p8"]
            view["rules"] += [
                reference(doc, path + f"/p8/rule_hits/{i}")
                for i in range(len(p8["rule_hits"]))
            ]
            view["assessments"].append(reference(doc, path + "/p8/rule_assessments"))
            view["interactions"].append(reference(doc, path + "/p8/time_interactions"))
        else:
            view["flying"].append(reference(doc, path + "/p8_flying_transformations"))


def _astro_documents(preview: dict, adapter: P8ChartAdapter, instant: dict) -> None:
    scope, sources = preview["scope"], source_hashes()
    birth = {
        "solar_datetime": BIRTH["date"] + " " + BIRTH["reported_time"],
        "calendar": "solar",
        "time_precision": "exact",
        "timezone_offset": instant["offset_minutes"] / 60,
        "location": {"lng": BIRTH["place"]["lon"], "lat": BIRTH["place"]["lat"]},
        "input_status": {"all_fields": "synthetic_fixture_not_user_fact"},
    }
    archive = {
        "owner_user_id": scope["owner_user_id"],
        "subject_id": scope["subject_id"],
        "user": {"birth": birth},
    }
    bundle = adapter.calculate(
        archive, TARGET, ["astro"], scope["revision"], scope["subject_id"]
    )
    if bundle["errors"] or len(bundle["artifacts"]) != 1:
        raise ValueError("synthetic_astro_calculation_failed")
    doc = document(scope, "calculation_bundle", sources, bundle)
    preview["documents"].append(doc)
    key = next(iter(bundle["artifacts"]))
    path = f"/artifacts/{key}/data"
    preview["view"]["primary"].append(reference(doc, path))
    preview["view"]["transits"].append(reference(doc, path + "/p8_transit_windows"))
    for technique in ("secondary_progressions", "solar_return"):
        args = {"birth_at": instant["utc"]}
        if technique == "secondary_progressions":
            args["target_at"] = TARGET + "T00:00:00Z"
        else:
            args.update(
                return_year=2026,
                longitude=BIRTH["place"]["lon"],
                latitude=BIRTH["place"]["lat"],
            )
        raw = adapter.western_timing(dict(scope, technique=technique, args=args))
        timing = document(scope, "western_timing", sources, raw)
        preview["documents"].append(timing)
        preview["view"]["timings"].append(reference(timing, "/data"))


def _binding(preview: dict, doc: dict, path: str) -> tuple[str, str]:
    if doc["kind"] == "time_basis":
        if path.startswith("/boundary_alerts/"):
            return boundary_binding(doc["payload"], path)
        if path.startswith("/charts/"):
            chart = doc["payload"]["charts"][int(path.split("/")[2])]
            return chart["id"], chart["time_basis"]["basis"]
        valid = [
            row
            for row in doc["payload"]["time_basis"]["instants"]
            if row["status"] == "valid"
        ]
        return valid[0]["id"], "actual_UTC"
    bundle = next(
        row["payload"]
        for row in preview["documents"]
        if row["kind"] == "calculation_bundle"
    )
    return next(iter(bundle["artifacts"].values()))["branch_id"], "actual_UTC"


def _aliases(preview: dict) -> None:
    docs = {row["document_id"]: row for row in preview["documents"]}
    refs = {
        (ref["document_id"], ref["path"])
        for group in preview["view"].values()
        for ref in group
    }
    rule_records = []
    for ref in rule_refs(preview):
        doc = docs[ref["document_id"]]
        hit = resolve(doc["payload"], ref["path"])
        _, evidence = rule_evidence(doc, ref["path"], hit)
        refs.update((item["document_id"], item["path"]) for item in evidence)
        rule_records.append((ref, hit, evidence))
    by_ref = {}
    for index, (ident, path) in enumerate(sorted(refs), 1):
        doc = docs[ident]
        branch, basis = _binding(preview, doc, path)
        row = alias(f"c{index}", preview["scope"], doc, path, branch, basis)
        preview["aliases"]["c"].append(row)
        by_ref[(ident, path)] = row["alias"]
    for index, (ref, hit, evidence) in enumerate(rule_records, 1):
        doc = docs[ref["document_id"]]
        branch, basis = _binding(preview, doc, ref["path"])
        version, _ = rule_evidence(doc, ref["path"], hit)
        row = alias(
            f"r{index}",
            preview["scope"],
            doc,
            ref["path"],
            branch,
            basis,
            rule_id=hit["rule_id"],
            rules_version=version,
            evidence_aliases=[
                by_ref[(item["document_id"], item["path"])] for item in evidence
            ],
        )
        preview["aliases"]["r"].append(row)


def build_preview(system: str, chart_python: str) -> dict:
    if system not in ("bazi", "ziwei", "astro"):
        raise ValueError("synthetic_preview_system_not_supported")
    scope = _scope(system)
    end = (datetime.fromisoformat(TARGET) + timedelta(days=7)).date().isoformat()
    period = {
        "start_at": TARGET + "T00:00:00Z",
        "end_at": end + "T00:00:00Z",
        "moving_bodies": ["月亮", "太阳"],
        "step_hours": 1,
    }
    adapter = P8ChartAdapter(
        scope["owner_user_id"], chart_python, timeout=120, transit_period=period
    )
    with offline_runtime():
        raw = adapter.time_basis(dict(scope, birth=deepcopy(BIRTH), as_of_date=TARGET))
        valid = [
            row for row in raw["time_basis"]["instants"] if row["status"] == "valid"
        ]
        if len(valid) != 1 or raw["time_basis"]["requires_confirmation"]:
            raise ValueError("synthetic_preview_requires_unambiguous_physical_instant")
        preview = _base(system, scope, valid[0]["utc"])
        basis_doc = document(scope, "time_basis", raw["source_sha256"], raw)
        preview["documents"].append(basis_doc)
        if system == "astro":
            preview["view"]["time_basis"] = [
                reference(basis_doc, "/time_basis/instants/0")
            ]
            _astro_documents(preview, adapter, valid[0])
        else:
            _basis_views(preview, basis_doc)
        add_boundary_views(preview, basis_doc)
        _aliases(preview)
    return preview


def main() -> None:
    from .handoff_validate import validate_preview

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted"], default="scripted")
    parser.add_argument("--chart-python", required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/v4/contracts"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "samples").mkdir(exist_ok=True)
    (args.output / "chart_compute.schema.json").write_text(
        json.dumps(schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
        newline="\n",
    )
    for system in ("bazi", "ziwei", "astro"):
        started = perf_counter()
        value = build_preview(system, args.chart_python)
        validate_preview(value, verify_runtime_sources=True)
        path = args.output / "samples" / f"ayuan_{system}.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf8",
            newline="\n",
        )
        print(
            json.dumps(
                {
                    "system": system,
                    "output": str(path),
                    "documents": len(value["documents"]),
                    "model_calls": 0,
                    "elapsed_seconds": round(perf_counter() - started, 6),
                }
            )
        )


if __name__ == "__main__":
    main()
