"""Opaque pure-kernel labels never replace the original PG authorization scope."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mingjing_core.domain.contracts import EvidenceError

from .streaming_kernel import load_kernel

if TYPE_CHECKING:
    from mingjing_core.integrations.streaming_candidate.event_models import RunScope


@dataclass(frozen=True)
class HostStreamScope:
    schema: str = field(repr=False)
    owner: str = field(repr=False)
    subject: str = field(repr=False)
    thread_id: str = field(repr=False)
    run_id: str = field(repr=False)

    def _label(self, domain: str) -> str:
        values = (self.schema, self.owner, self.subject, self.thread_id, self.run_id)
        if any(type(value) is not str or not value for value in values):
            raise EvidenceError("流式内部范围格式无效")
        try:
            raw = json.dumps(["mingjing-p4-scope-v1", domain, *values], ensure_ascii=False).encode("utf-8")
        except UnicodeError:
            raise EvidenceError("流式内部范围编码无效") from None
        return domain + "_" + hashlib.sha256(raw).hexdigest()

    def kernel_scope(self) -> RunScope:
        # This only labels a pure buffer. Host services must still verify the real values in PG.
        return load_kernel().RunScope(self._label("owner"), self._label("run"))
