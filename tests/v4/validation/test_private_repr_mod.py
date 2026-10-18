"""Context and mutation diagnostics must not turn private content into repr logs."""

import json
from datetime import UTC, datetime

import pytest

from mingjing_core.organize._change_values import FieldValue
from mingjing_core.organize.contracts import Message, Topic
from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.legacy_lint import LintContext
from mingjing_core.validation.structural import StructuralContext, structural_check

MARKER = "SYNTHETIC_PRIVATE_DIAGNOSTIC_MARKER"


def test_context_message_topic_and_field_value_hide_private_strings_from_repr() -> None:
    values = [
        Message("m", "user", MARKER, 0, "o", "s"),
        Topic("t", "daily", MARKER, (), (), 0, 0, (), MARKER),
        FieldValue(True, json.dumps({"title": MARKER})),
        LintContext({"facts": [MARKER]}, {"claims": [MARKER]}, {"field": MARKER}, {"message": MARKER}),
    ]
    assert all(MARKER not in repr(value) for value in values)


@pytest.mark.parametrize("receipt", [None, {"write_status": {}}, {"write_status": []}])
def test_bad_receipt_metadata_does_not_bypass_false_receipt_check(receipt: object) -> None:
    context = StructuralContext(FrozenClock(datetime(2026, 10, 18, tzinfo=UTC)), receipts=(receipt,))
    result = structural_check("我已经保存了。", context)
    assert "这条还没有真正保存" in result.text
    assert not any(finding.code == "structural_internal_error" for finding in result.findings)
