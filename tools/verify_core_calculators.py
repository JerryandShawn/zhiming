"""Repeat isolated calculation checks using synthetic data; no model/network/DB.

Run with the interpreter containing requirements-charts.lock. An absent native
dependency is a failure, not an accepted skip. The optional JSON report contains
only fixed synthetic vectors, software provenance and aggregate test statistics.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify():
    required = ("lunar_python", "py_iztro", "pythonmonkey", "swisseph")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("isolated chart dependency missing: " + ", ".join(missing))
    tests = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest",
                            "tests.test_core_charts", "tests.test_core_knowledge",
                            "tests.test_core_calculation_boundaries"], cwd=ROOT,
                           text=True, encoding="utf-8", capture_output=True, timeout=120)
    log = tests.stdout + tests.stderr
    found = re.search(r"Ran (\d+) tests", log)
    if tests.returncode or not found or "skipped=" in log:
        raise RuntimeError("calculator tests did not pass without skips:\n" + log)
    from mingjing_core.adapters.charts import ChartsAdapter
    from mingjing_core.knowledge import KnowledgeRegistry
    from tests.test_core_charts import archive
    result = ChartsAdapter("owner-a", python=sys.executable).run(archive(), "2026-10-11", ["bazi", "ziwei", "astro"], 7, "self")
    if result["errors"]: raise RuntimeError("synthetic calculation failed")
    registry = KnowledgeRegistry.load_builtin()
    claims = registry.claims_for(result, "owner-a", "self", 7, "study", "all", "2026-10-11")
    if claims["gaps"]: raise RuntimeError("released structural rule has a gap for complete synthetic vector")
    software = {}
    for name in ("lunar-python", "py-iztro", "pythonmonkey", "pyswisseph"):
        metadata = importlib.metadata.metadata(name)
        software[name] = {"version": importlib.metadata.version(name), "license_metadata": metadata.get("License", "not_exposed")[:300]}
    return {"schema_version": "core-calculation-validation-v1", "checked_at": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version.split()[0], "synthetic_only": True,
            "tests": {"run": int(found.group(1)), "passed": int(found.group(1)), "skipped": 0},
            "pack": {"version": registry.pack_version, "hash": registry.pack_hash, "rules": len(registry._rules),
                     "sources": len(registry._sources), "cards": len(registry._cards)},
            "chart_rules_exercised": sorted(c["rule_id"] for c in claims["claims"]),
            "software": software, "actual_profiles": {p["system"]: {key: p[key] for key in ("actual_method", "versions", "warnings", "fallback")}
                                                     for p in result["profiles"].values()},
            "license_evidence": {"swisseph": "https://github.com/aloistr/swisseph/blob/master/LICENSE",
                                 "pyswisseph": "https://github.com/astrorigin/pyswisseph/blob/master/LICENSE.txt",
                                 "attestation": "Deployment authorization is recorded separately; tests do not verify license contracts."},
            "limits": ["Finite time samples are not continuous coverage.", "Ziwei upstream version is a distribution declaration, not independent verification.",
                       "No full strength/useful-god, flying-palace, dignity, progression or exact event prediction is claimed."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify()
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "tests": report["tests"], "pack": report["pack"]}, ensure_ascii=False))
