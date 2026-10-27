"""Report-local aliases remain bound to the full original document/path/claim rather than a short name."""

from collections.abc import Sequence
from datetime import datetime

from mingjing_core.application.briefing_v2.contracts import BasisRef

from .contracts import ReportCitation, ReportError, ReportLine


class CitationRegistry:
    def __init__(self) -> None:
        self._known: dict[tuple[str, str], ReportCitation] = {}
        self._counts: dict[str, int] = {}

    def line(
        self,
        value: str,
        basis: Sequence[BasisRef],
        *,
        event_at: datetime | None = None,
        said_at: datetime | None = None,
    ) -> ReportLine:
        citations = tuple(self._register(ref) for ref in basis)
        return ReportLine(value, citations, event_at, said_at)

    def _register(self, ref: BasisRef) -> ReportCitation:
        if not isinstance(ref, BasisRef):
            raise ReportError("citation_basis_required")
        key = (ref.document_id or ref.source_id, ref.alias)
        if key in self._known:
            if self._known[key].basis != ref:
                raise ReportError("same_document_alias_rebound")
            return self._known[key]
        prefix = ref.alias[0]
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        citation = ReportCitation(f"{prefix}{self._counts[prefix]}", ref.alias, ref)
        self._known[key] = citation
        return citation

    def all(self) -> tuple[ReportCitation, ...]:
        return tuple(self._known.values())
