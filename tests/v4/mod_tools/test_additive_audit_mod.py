"""Prevent a renamed/deleted baseline file from being misreported as a new-only delivery."""

from tools.mod_overnight.audit_additions import parse_name_status


def test_nul_parser_preserves_unicode_tabs_and_rename_source() -> None:
    raw = "A\0docs/新增\t说明.md\0R100\0old.py\0new.py\0D\0removed.py\0".encode()
    assert parse_name_status(raw) == [
        {"status": "A", "path": "docs/新增\t说明.md"},
        {"status": "R100", "path": "old.py", "new_path": "new.py"},
        {"status": "D", "path": "removed.py"},
    ]


def test_empty_git_diff_is_not_a_missing_file_error() -> None:
    assert parse_name_status(b"") == []
