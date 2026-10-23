"""Check that the copied legacy grammar retains every old literal regex, without printing it."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def verify() -> dict[str, object]:
    source = (ROOT / "mingjing_core/application/consultation.py").read_text(encoding="utf-8")
    method = next(
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == "_validate"
    )
    literals = [
        node.args[0].value
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    copied = set()
    modules = sorted((ROOT / "mingjing_core/validation").glob("legacy*.py"))
    for module in modules:
        copied.update(
            node.value
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    return {
        "source_function_sha256": hashlib.sha256(ast.get_source_segment(source, method).encode()).hexdigest(),
        "old_literal_regex_occurrences": len(literals),
        "old_unique_literal_regexes": len(set(literals)),
        "missing_unique_regexes": len(set(literals) - copied),
        "copied_modules": len(modules),
        "scope": "Literal retention is supplementary evidence; differential behavior tests establish parity.",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
