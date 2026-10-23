"""Eight-section literal Markdown from current source-bound entries, never an automatic profile write."""

import html
import re

from mingjing_core.memory2.contracts import Confirmation, MemoryScope, MemorySettings, MemorySnapshot
from mingjing_core.memory2.reflection import SECTION_TITLES
from mingjing_core.timekit.clock import Clock

from .profile_contracts import AboutMeSection, AboutMeView, ProfileDocument, ProfileLine
from .profile_guard import current_profile_items
from .validation import instant


def literal(value: str) -> str:
    # Escape HTML and Markdown control characters; UI must still apply its normal sanitized renderer.
    escaped = html.escape(value.replace("\r", " ").replace("\n", " "), quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", escaped)


def render_about_me(
    document: ProfileDocument,
    *,
    snapshot: MemorySnapshot,
    scope: MemoryScope,
    clock: Clock,
    current_profile_revision: int | None = None,
    settings: MemorySettings | None = None,
    confirmations: tuple[Confirmation, ...] = (),
) -> AboutMeView:
    entries, omitted, warnings = current_profile_items(
        document,
        snapshot=snapshot,
        scope=scope,
        clock=clock,
        current_profile_revision=current_profile_revision,
        settings=settings,
        confirmations=confirmations,
    )
    sections = []
    for number, title in SECTION_TITLES.items():
        lines = tuple(
            ProfileLine(
                row.item.id,
                number,
                row.item.text,
                row.origin,
                row.item.source_ids,
                row.item.fact_ids,
                row.anchors,
                row.item.confidence,
                row.item.pinned,
                row.item.edited_by_user,
            )
            for row in entries
            if row.item.section == number
        )
        sections.append(AboutMeSection(number, title, lines))
    markdown = _markdown(tuple(sections))
    return AboutMeView(
        scope,
        document.revision,
        snapshot.revision,
        snapshot.source_epoch,
        instant(clock.now()),
        tuple(sections),
        markdown,
        omitted,
        warnings,
    )


def _markdown(sections: tuple[AboutMeSection, ...]) -> str:
    text = ["# 明镜台眼中的你", "", "以下只显示当前来源仍有效的条目；推测与用户原话分开，未执行任何更新。", ""]
    aliases: dict[str, str] = {}
    for section in sections:
        text.extend((f"## {section.number}. {section.title}", ""))
        if not section.lines:
            text.extend(
                ("命理档案尚无权威契约验证，未展示盘面判断。" if section.number == 7 else "暂无当前有效条目。", "")
            )
            continue
        for line in section.lines:
            label = "推测（不是用户原话）" if line.origin == "analysis" else "依据用户事实的条目"
            flags = "；用户编辑" if line.edited_by_user else "；已固定" if line.pinned else ""
            text.append(f"- {label}{flags}：{literal(line.text)}")
            for anchor in line.anchors:
                key = anchor.source_id + ":" + str(anchor.revision) + ":" + str(anchor.start) + ":" + str(anchor.end)
                aliases.setdefault(key, f"m{len(aliases) + 1}")
                text.append(f"  - 用户原话〔{aliases[key]}〕：{literal(anchor.quote)}")
        text.append("")
    text.append("已发出的外部消息不在本纯渲染模块的撤回范围；来源撤销后须重新查询并刷新页面。")
    return "\n".join(text) + "\n"
