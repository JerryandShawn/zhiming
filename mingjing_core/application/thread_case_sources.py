"""Bind authenticated selections on first intake; a replay cannot widen original scope."""

from __future__ import annotations

from typing import Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError


def normalize_case_ids(case_ids: Any) -> list[str]:
    if case_ids is None:
        return []
    if (
        type(case_ids) is not list
        or len(case_ids) > 8
        or any(type(ident) is not str or not ident.strip() or len(ident) > 200 for ident in case_ids)
    ):
        raise EvidenceError("原话事项选择需要至多8个有效标识")
    return list(dict.fromkeys(case_ids))


def selected_cases(repo: Any, owner: str, subject: str, case_ids: Any, *, private: bool = False) -> list[str]:
    cases = normalize_case_ids(case_ids)
    if private and cases:
        raise EvidenceError("无痕原话不能绑定长期事项")
    repo.assert_scope(owner, subject)
    for ident in cases:
        row = repo.get(owner, "case", ident, include_deleted=True)
        if row["subject_id"] != subject:
            raise ScopeError("原话事项不属于当前人物")
        if row["status"] in {"deleted", "stopped", "superseded"} or repo.is_revoked(owner, "case", ident):
            raise EvidenceError("已撤销的事项不能授权新原话")
    return cases


def same_case_selection(original: dict[str, Any], selected: list[str]) -> None:
    if original.get("case_ids", []) != selected:
        raise EvidenceError("已存在原话不能追加、移除或改变事项选择")


def bind_case_selection(identity: list[Any], selected: list[str]) -> list[Any]:
    # Preserve bytes of existing empty-selection privacy receipts.
    return identity + [{"case_ids": selected}] if selected else identity
