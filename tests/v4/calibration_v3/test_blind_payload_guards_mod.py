"""Target-item hints invalidate a blind view even if an attestor signed the wrong view."""

import copy
import hashlib
import hmac
from dataclasses import replace

import pytest

from tools.calibration_v3.batches import blind_payload
from tools.calibration_v3.blind_payload_contract import blind_payload_digest
from tools.calibration_v3.human_provenance import HmacHostVerifier, attestation_bytes, verify_human_record
from tools.calibration_v3.models import CalibrationError, fingerprint

from .calibration_toy_support_mod import toy_plan
from .test_human_provenance_mod import TEST_KEY, protocol_record


@pytest.mark.parametrize("name", ["item", "gold", "expected", "reason", "source_id", "title", "critic_result"])
def test_candidate_view_rejects_every_answer_key_hint_field(name: str) -> None:
    dataset, plan = toy_plan()
    payload = blind_payload(dataset, plan, plan.batches[0])
    payload["candidates"][0][name] = "SYNTHETIC_HINT"
    with pytest.raises(CalibrationError, match="blind_candidate_fields_invalid"):
        blind_payload_digest(payload)


@pytest.mark.parametrize("change", ["extra-top-field", "duplicate-case", "empty-material", "old-schema"])
def test_blind_batch_has_a_strict_schema_and_complete_unique_cases(change: str) -> None:
    dataset, plan = toy_plan()
    payload = blind_payload(dataset, plan, plan.batches[0])
    if change == "extra-top-field":
        payload["item"] = "E1"
    elif change == "duplicate-case":
        payload["candidates"][-1] = copy.deepcopy(payload["candidates"][0])
    elif change == "empty-material":
        payload["candidates"][0]["material"] = ""
    else:
        payload["schema"] = "blind-review-batch-v3"
    with pytest.raises(CalibrationError):
        blind_payload_digest(payload)


def test_valid_host_signature_for_leaky_old_payload_is_not_a_corrected_blind_review() -> None:
    record, plan, ledger, clock, dataset = protocol_record()
    old = blind_payload(dataset, plan, plan.batches[0])
    old["candidates"][0]["item"] = plan.batches[0].refs[0].item
    changed = replace(record, payload_sha256=fingerprint(old))
    changed = replace(changed, signature=hmac.new(TEST_KEY, attestation_bytes(changed), hashlib.sha256).hexdigest())
    with pytest.raises(CalibrationError, match="human_displayed_payload_mismatch"):
        verify_human_record(
            changed, plan=plan, dataset=dataset, ledger=ledger, verifier=HmacHostVerifier(TEST_KEY), clock=clock
        )
