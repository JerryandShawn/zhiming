"""Pin both verified byte artifacts; cross-platform EOL support must not relax frozen content."""

import hashlib
import json
from pathlib import Path

import pytest

from .calendar_acceptance_support_mod import EXPECTED_LF_SHA, EXPECTED_SHA, frozen_expected_bytes


def frozen_variants() -> tuple[bytes, bytes]:
    original = (Path(__file__).parent / "fixtures/expected_calendar_mod.json").read_bytes()
    lf = original.replace(b"\r\n", b"\n")
    return lf, lf.replace(b"\n", b"\r\n")


def test_only_verified_eol_variants_have_frozen_hashes_and_identical_semantics() -> None:
    lf, crlf = frozen_variants()
    assert hashlib.sha256(lf).hexdigest() == EXPECTED_LF_SHA
    assert hashlib.sha256(crlf).hexdigest() == EXPECTED_SHA
    assert b"\r" not in lf and crlf.count(b"\r\n") == lf.count(b"\n")
    assert crlf.replace(b"\r\n", b"\n") == lf
    assert json.loads(lf) == json.loads(crlf)
    assert frozen_expected_bytes(lf) == frozen_expected_bytes(crlf)
    assert len(frozen_expected_bytes(lf)["semantic_groups"]) == 18


@pytest.mark.parametrize("variant", (0, 1))
@pytest.mark.parametrize("field", ("schema_version", "semantic_groups", "random_plan"))
def test_substantive_change_is_rejected_for_both_eol_variants(variant: int, field: str) -> None:
    original = frozen_variants()[variant]
    value = json.loads(original)
    if field == "schema_version":
        value[field] = "changed-independent-contract"
    elif field == "semantic_groups":
        value[field] = value[field][:-1]
    else:
        value[field]["idle_cases"] += 1
    changed = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
    if variant:
        changed = changed.replace(b"\n", b"\r\n")
    assert json.loads(changed) != json.loads(original)
    with pytest.raises(AssertionError):
        frozen_expected_bytes(changed)


@pytest.mark.parametrize("variant", (0, 1))
def test_unlisted_whitespace_or_mixed_eol_is_not_silently_allowed(variant: int) -> None:
    original = frozen_variants()[variant]
    for changed in (b" " + original, original + b"\n", original.replace(b"\n", b"\r\n", 1)):
        with pytest.raises(AssertionError):
            frozen_expected_bytes(changed)
