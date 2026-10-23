"""Protect verbatim grammar while the legacy runtime remains alongside new lint."""

from tools.mod_overnight.verify_legacy_parity import verify


def test_all_old_literal_regexes_remain_available_without_changing_legacy_source() -> None:
    result = verify()
    assert result["old_literal_regex_occurrences"] == 99
    assert result["old_unique_literal_regexes"] == 81
    assert result["missing_unique_regexes"] == 0
