"""Pure frozen snapshots; persistent confirmation and audit belong to main line."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from typing import Any

from .contracts import canonical, digest, rules, rules_identity


def seed(session_id: str, purpose: str) -> int:
    return int(digest([session_id, purpose])[:16], 16)


def events_digest(rows: tuple[str, ...]) -> str:
    return digest([json.loads(row) for row in rows])


def _events(
    rows: list[dict[str, Any]], birth_year: int, asof: int, round_no: int
) -> tuple[str, ...]:
    normalized, ids, sources = [], set(), set()
    for row in rows:
        ident, kind, year = row.get("id"), row.get("type"), row.get("year")
        if (
            not isinstance(ident, str)
            or not ident
            or ident in ids
            or kind not in rules()["event_rules"]
        ):
            raise ValueError("invalid_or_duplicate_event_identity")
        if type(year) is not int or not birth_year + 6 <= year <= asof:
            raise ValueError("event_year_outside_precomputed_observation_range")
        lower, upper = rules()["age_intervals"][kind]
        if not lower <= year - birth_year <= upper:
            raise ValueError("event_outside_project_type_age_interval")
        month, certainty = row.get("month"), row.get("certainty", "unsure")
        if month is not None and (type(month) is not int or not 1 <= month <= 12):
            raise ValueError("invalid_event_month")
        if (
            certainty not in ("sure", "roughly", "unsure")
            or row.get("added_in_round", round_no) != round_no
        ):
            raise ValueError("invalid_event_certainty_or_round")
        source = row.get("source_fact_id", row.get("source_id"))
        if source is not None and (
            not isinstance(source, str) or not source or source in sources
        ):
            raise ValueError("duplicate_or_invalid_event_source")
        ids.add(ident)
        if source is not None:
            sources.add(source)
        normalized.append(
            {
                "id": ident,
                "type": kind,
                "year": year,
                "month": month,
                "certainty": certainty,
                "source_fact_id": source,
                "added_in_round": round_no,
            }
        )
    return tuple(
        canonical(row) for row in sorted(normalized, key=lambda row: row["id"])
    )


@dataclass(frozen=True)
class FrozenSession:
    session_id: str
    scope: tuple[str, str, int]
    birth_year: int
    as_of_year: int
    first: tuple[str, ...]
    second: tuple[str, ...]
    events_hash: str
    round2_hash: str | None
    rules_version: str
    rules_hash: str
    revocations: tuple[str, ...] = ()

    def verify(self) -> None:
        if (self.rules_version, self.rules_hash) != rules_identity():
            raise ValueError("frozen_rules_changed_new_session_required")
        if events_digest(self.first) != self.events_hash or (
            self.second and events_digest(self.second) != self.round2_hash
        ):
            raise ValueError("frozen_events_changed_no_year_edits_allowed")
        if self.revocations:
            raise ValueError("basis_revoked_result_invalid_recompute_required")

    def event_rows(self, round_no: int) -> list[dict[str, Any]]:
        self.verify()
        if round_no not in (1, 2) or (round_no == 2 and not self.second):
            raise ValueError("round_not_available_maximum_two_rounds")
        return [
            json.loads(row)
            for row in self.first + (self.second if round_no == 2 else ())
        ]


def freeze_round1(
    session_id: str,
    events: list[dict[str, Any]],
    *,
    owner_user_id: str,
    subject_id: str,
    revision: int,
    birth_year: int,
    as_of_year: int,
    user_confirmed: bool,
) -> FrozenSession:
    if user_confirmed is not True or not all(
        isinstance(x, str) and x.strip()
        for x in (session_id, owner_user_id, subject_id)
    ):
        raise ValueError("explicit_user_confirmation_and_scope_required")
    if (
        type(revision) is not int
        or revision < 0
        or type(birth_year) is not int
        or type(as_of_year) is not int
    ):
        raise ValueError("invalid_scope_revision_or_year")
    if not isinstance(events, list) or not 1 <= len(events) <= 50:
        raise ValueError("need_one_to_fifty_confirmed_events")
    normalized = _events(events, birth_year, as_of_year, 1)
    version, rule_hash = rules_identity()
    return FrozenSession(
        session_id,
        (owner_user_id, subject_id, revision),
        birth_year,
        as_of_year,
        normalized,
        (),
        events_digest(normalized),
        None,
        version,
        rule_hash,
    )


def freeze_round2(
    session: FrozenSession, additions: list[dict[str, Any]], *, user_confirmed: bool
) -> FrozenSession:
    session.verify()
    if (
        user_confirmed is not True
        or not additions
        or len(session.first) + len(additions) > 50
    ):
        raise ValueError("confirmed_round_two_additions_required")
    second = _events(additions, session.birth_year, session.as_of_year, 2)
    if session.second:
        if session.second == second:
            return session
        raise ValueError("maximum_two_rounds_no_additional_updates")
    all_rows = [json.loads(row) for row in session.first + second]
    ids = [row["id"] for row in all_rows]
    sources = [
        row["source_fact_id"] for row in all_rows if row["source_fact_id"] is not None
    ]
    if len(set(ids)) != len(ids) or len(set(sources)) != len(sources):
        raise ValueError("frozen_event_or_source_cannot_be_replaced_or_repeated")
    return replace(session, second=second, round2_hash=events_digest(second))


def revoke_event(session: FrozenSession, event_id: str, reason: str) -> FrozenSession:
    rows = session.event_rows(2 if session.second else 1)
    if event_id not in {row["id"] for row in rows} or not reason.strip():
        raise ValueError("explicit_existing_event_and_revocation_reason_required")
    return replace(
        session,
        revocations=session.revocations
        + (canonical({"event_id": event_id, "reason": reason}),),
    )


def split_events(
    session: FrozenSession, round_no: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = session.event_rows(round_no)
    if len(rows) < 6:
        return rows, []
    indices = list(range(len(rows)))
    random.Random(seed(session.session_id, "holdout")).shuffle(indices)
    held = set(indices[: max(1, round(len(rows) / 3))])
    return [row for index, row in enumerate(rows) if index not in held], [
        row for index, row in enumerate(rows) if index in held
    ]
