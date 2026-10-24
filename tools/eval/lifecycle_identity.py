"""Read-only candidate and native central identity for private evaluation state."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from mingjing_core.models.quota_guard import QuotaGuard
from tools.eval.contracts import scenario_contract_hash
from tools.eval.live import candidate_provenance
from tools.eval.schema import Scenario
from tools.eval.targets.local_db import verify_local_postgres


class LifecycleError(ValueError):
    code = "EVAL_LIFECYCLE_REJECTED"


@dataclass(frozen=True)
class LifecycleBinding:
    candidate_commit: str
    source_sha256: str
    model: str
    scenario_id: str
    contract_sha256: str
    central_account: str
    central_identity: str
    central_location: str

    def __post_init__(self) -> None:
        from tools.eval.targets.v4_core30 import CORE30_IDS

        if (
            re.fullmatch(r"[0-9a-f]{40}", self.candidate_commit or "") is None
            or any(
                re.fullmatch(r"[0-9a-f]{64}", value or "") is None
                for value in (self.source_sha256, self.contract_sha256, self.central_location)
            )
            or self.model not in {"k3", "k3-256k"}
            or self.scenario_id not in CORE30_IDS
        ):
            raise LifecycleError("生命周期绑定只接受固定core30契约和K3模型")

    def _contract(self) -> None:
        from tools.eval.targets.v4_core30 import load_core30

        scenario = next(case for case in load_core30() if case.id == self.scenario_id)
        if scenario_contract_hash(scenario) != self.contract_sha256:
            raise LifecycleError("场景契约已经改变")

    @classmethod
    def capture(cls, guard: QuotaGuard, candidate: str, scenario: Scenario, model: str) -> LifecycleBinding:
        from tools.eval.runner import ROOT, _source_digest

        if re.fullmatch(r"[0-9a-f]{40}", candidate or "") is None or model not in {"k3", "k3-256k"}:
            raise LifecycleError("评测候选与模型身份无效")
        candidate_provenance(ROOT, candidate)
        verify_local_postgres(guard.store.dsn)
        with guard.store.connect() as connection:
            account = guard.store.verify(connection)
        result = cls(
            candidate,
            _source_digest(),
            model,
            scenario.id,
            scenario_contract_hash(scenario),
            guard.store.account_id,
            guard.store.identity,
            account["location_id"],
        )
        result._contract()
        return result

    def verify(self, guard: QuotaGuard) -> dict[str, Any]:
        from tools.eval.runner import ROOT, _source_digest

        candidate_provenance(ROOT, self.candidate_commit)
        self._contract()
        verify_local_postgres(guard.store.dsn)
        with guard.store.connect() as connection:
            account = guard.store.verify(connection)
        if (self.source_sha256, self.central_account, self.central_identity, self.central_location) != (
            _source_digest(),
            guard.store.account_id,
            guard.store.identity,
            account["location_id"],
        ):
            raise LifecycleError("评测执行来源或中央身份已经改变")
        return asdict(self)
