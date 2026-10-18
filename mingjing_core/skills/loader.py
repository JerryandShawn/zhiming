"""Read-only, allowlisted progressive disclosure of product skill chapters."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MAX_CONTEXT_UTF8_BYTES = 5_500
ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class SkillLibrary:
    """Loads local reviewed assets only; neither executes code nor accesses I/O services."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()
        self.catalog = json.loads(
            (self.root / "catalog.json").read_text(encoding="utf-8")
        )

    def chapters(self, system: str) -> list[dict[str, Any]]:
        """Return fresh metadata, without loading chapter text into the context."""
        return deepcopy(self._system(system)["chapters"])

    def _system(self, system: str) -> dict[str, Any]:
        if (
            not isinstance(system, str)
            or not ID.fullmatch(system)
            or system not in self.catalog["systems"]
        ):
            raise ValueError("未知命理技能体系")
        return self.catalog["systems"][system]

    def load(self, system: str, topic: str) -> dict[str, Any]:
        package = self._system(system)
        if not isinstance(topic, str) or not ID.fullmatch(topic):
            raise ValueError("未知命理技能章节")
        matches = [row for row in package["chapters"] if row["topic"] == topic]
        if len(matches) != 1:
            raise ValueError("未知命理技能章节")
        metadata = deepcopy(matches[0])
        text = self._read_chapter(system, metadata["file"])
        version = self.catalog["version"]
        context = f'<技能 system="{system}" topic="{topic}" version="{version}">\n{text}\n</技能>'
        size = len(context.encode("utf-8"))
        if size > MAX_CONTEXT_UTF8_BYTES:
            raise ValueError("章节超出保守上下文预算，请拆分章节")
        return {
            "system": system,
            "topic": topic,
            "version": version,
            "metadata": metadata,
            "text": text,
            "context": context,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "context_utf8_bytes": size,
            "token_budget": {
                "limit": 6000,
                "accounted_units": size,
                "accounting": "UTF-8 bytes as conservative proxy; not a measured model-token count",
                "runtime_requirement": "主线装配时仍须按实际模型 tokenizer 验证总上下文预算",
            },
        }

    def _read_chapter(self, system: str, filename: str) -> str:
        if Path(filename).name != filename or not filename.endswith(".md"):
            raise ValueError("技能目录中的章节路径无效")
        package = (self.root / system).resolve()
        path = (package / filename).resolve()
        if not package.is_relative_to(self.root) or not path.is_relative_to(package):
            raise ValueError("技能章节不能越过产品技能目录")
        return path.read_text(encoding="utf-8")


def chart_skill(system: str, topic: str) -> dict[str, Any]:
    """Standalone adapter for later Agent-tool wiring; deliberately has no side effects."""
    return SkillLibrary().load(system, topic)
