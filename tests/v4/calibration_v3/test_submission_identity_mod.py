"""Compare the actual frontend JSON Schema against strict semantic identity validation."""

import pytest
from jsonschema import Draft202012Validator

from tools.calibration_v3.models import CalibrationError, identity
from tools.calibration_v3.submission import validate_submission

from .test_submission_mod import SCHEMA, submission


@pytest.mark.parametrize(
    "value",
    [
        *(chr(code) + "owner" for code in range(32)),
        *("owner" + chr(code) for code in range(32)),
        "",
        " ",
        "\u2003",
        "  \u2003  ",
        "x" * 161,
        "owner-1",
        "user:12",
        "甲",
        "  owner  ",
        "x" * 160,
    ],
)
def test_schema_identity_and_semantic_identity_agree_for_control_blank_and_normal_ids(value: str) -> None:
    for field in ("owner_id", "reviewer_id", "submission_id"):
        schema_ok = not list(Draft202012Validator(SCHEMA["properties"][field]).iter_errors(value))
        try:
            identity(value)
            semantic_ok = True
        except CalibrationError:
            semantic_ok = False
        assert schema_ok is semantic_ok


@pytest.mark.parametrize("value", ["\x00owner", "owner\n", "\x1fowner", " "])
def test_real_full_submission_schema_and_semantic_entry_both_reject_control_or_blank_submission_id(value: str) -> None:
    payload, dataset, plan, ledger, clock = submission()
    payload["submission_id"] = value
    assert list(Draft202012Validator(SCHEMA).iter_errors(payload))
    with pytest.raises(CalibrationError):
        validate_submission(payload, dataset=dataset, plan=plan, ledger=ledger, clock=clock)
