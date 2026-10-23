"""Public correlation IDs never replace or disclose opaque private protocol IDs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint

OPAQUE_PREFIX = "p3opaque:"
PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}")


def public_call_id(run: Mapping[str, Any], raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        raise EvidenceError("公开工具关联标识缺少有效私有调用身份")
    if PUBLIC_ID.fullmatch(raw) is not None and not raw.startswith(OPAQUE_PREFIX):
        return raw
    ident, epoch = run.get("id"), run.get("retry_epoch")
    if not isinstance(ident, str) or type(epoch) is not int or epoch < 0:
        raise EvidenceError("公开工具关联标识缺少当前运行批次")
    # Reserving the prefix prevents a legal raw ID from impersonating the
    # deterministic output. This is a correlation label, never a lookup key.
    return OPAQUE_PREFIX + fingerprint([ident, epoch, raw])
