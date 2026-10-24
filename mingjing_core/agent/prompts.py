"""Pinned official prompt artifacts; runtime substitution never rewrites their prose."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mingjing_core.domain.contracts import EvidenceError

MANIFEST_SHA256 = "7232495299c25c9fafc6576fcd043696accd903a04645fcbd304a75212190d9a"
DIRECTORY = Path(__file__).with_suffix("")


@dataclass(frozen=True)
class PromptBundle:
    texts: dict[str, str]
    manifest: dict[str, Any]

    def render(self, name: str) -> str:
        value = self.texts[name].replace("{{assistant_name_line}}", "")
        value = re.sub(r"\{\{L[1-6]_[^}]+\}\}", "", value)
        if "{{" in value or "}}" in value:
            raise EvidenceError("运行时提示词存在未处理的占位符")
        return value.strip()

    def system(self, *, onboarding: bool = False, crisis: bool = False) -> str:
        names = ["system"] + (["onboarding"] if onboarding else [])
        return "\n\n".join(self.render(name) for name in names)


def load_prompts() -> PromptBundle:
    path = DIRECTORY / "manifest.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise EvidenceError("提示词清单版本或校验和不符")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "agent-prompts-v1" or set(manifest.get("files", {})) != {
        "system",
        "onboarding",
        "critic",
        "crisis",
    }:
        raise EvidenceError("提示词清单格式不符")
    texts = {}
    for name, row in manifest["files"].items():
        if row["file"] != name + ".md":
            raise EvidenceError("提示词文件路径不符")
        content = (DIRECTORY / row["file"]).read_bytes()
        header = "<!-- prompt: " + name + " v" + row["version"] + " -->"
        if hashlib.sha256(content).hexdigest() != row["sha256"] or not content.decode("utf-8").startswith(header):
            raise EvidenceError("提示词内容或版本不符")
        texts[name] = content.decode("utf-8")
    return PromptBundle(texts, manifest)
