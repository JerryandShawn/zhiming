"""Compute annual Bazi/U12 vectors once; Ziwei stays a separate unscored column."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from ..interactions_bazi import bazi_interactions
from ..named_bazi import hidden_for, options
from ..worker import load_engine
from .contracts import AnnualSignalCache, canonical, rules, rules_identity

RuleProvider = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _rule_hits(context: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    from ..rules import evaluate_rules

    data = context.get("data") or {
        "pillars": {
            name: {"ganzhi": value, "gan": value[0], "zhi": value[1]}
            for name, value in context["pillars"].items()
        },
        "p8": context["p8"],
    }
    return evaluate_rules(data, graph=graph)


def _pieces(context: dict[str, Any], year: int, engine: Any) -> list[datetime]:
    left, right = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    if context.get("as_of_date") is not None:
        cutoff = datetime.combine(
            date.fromisoformat(context["as_of_date"]), datetime.min.time()
        ) + timedelta(days=1)
        right = min(right, cutoff)
    if right <= left:
        raise ValueError("annual_signal_year_is_after_explicit_source_clock")
    points = {left, right}
    table = engine.Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
    for name in ("立春", "LI_CHUN"):
        points.add(datetime.fromisoformat(table[name].toYmdHms()))
    for row in context["p8"]["decade_luck"]["decades"]:
        for key in ("nominal_start_at", "nominal_end_exclusive"):
            points.add(datetime.fromisoformat(row[key]).replace(tzinfo=None))
    points = sorted(point for point in points if left <= point <= right)
    return [
        start + (end - start) / 2
        for start, end in zip(points[:-1], points[1:], strict=True)
    ]


def _graph(context: dict[str, Any], point: datetime, engine: Any) -> dict[str, Any]:
    lunar = engine.Solar.fromYmdHms(
        point.year, point.month, point.day, point.hour, point.minute, point.second
    ).getLunar()
    layers = {"yearly": lunar.getYearInGanZhiExact()}
    decade = next(
        (
            row
            for row in context["p8"]["decade_luck"]["decades"]
            if datetime.fromisoformat(row["nominal_start_at"]).replace(tzinfo=None)
            <= point
            < datetime.fromisoformat(row["nominal_end_exclusive"]).replace(tzinfo=None)
        ),
        None,
    )
    if decade is not None:
        layers["decadal"] = decade["ganzhi"]
    selected = {
        key: value
        for key, value in context["p8"]["selected_schools"].items()
        if key in ("command", "tianyi", "blade", "shen_earth")
    }
    return bazi_interactions(
        context["pillars"], layers, hidden_stems=hidden_for(options(selected))
    )


def _signal(
    signal: str, graph: dict[str, Any], hits: dict[str, Any]
) -> list[dict[str, Any]]:
    if signal.startswith("rule:"):
        return [
            {
                "kind": "rule",
                "rule_id": row["rule_id"],
                "paths": row["evidence_paths"],
                "version": hits["version"],
                "details": row["details"],
            }
            for row in hits["rule_hits"]
            if row["rule_id"] == signal[5:]
        ]
    parts = signal.split(".")
    if parts[0] == "tg":
        return [
            {
                "kind": "calculation",
                "node_id": row["id"],
                "ten_god": row["stem_ten_god"],
            }
            for row in graph["nodes"]
            if row["id"] == "target." + parts[1] and row["stem_ten_god"] == parts[2]
        ]
    if parts[0] != "u2" or len(parts) != 4:
        raise ValueError("unregistered_annual_signal")
    return [
        {"kind": "calculation", "relation_id": row["id"], "relation_kind": row["kind"]}
        for row in graph["relations"]
        if row["kind"] == parts[2]
        and row.get("complete", True)
        and {"target." + parts[1], "natal." + parts[3]}
        <= {member["id"] for member in row["members"]}
    ]


def _year_vector(
    context: dict[str, Any],
    year: int,
    signals: tuple[str, ...],
    engine: Any,
    provider: RuleProvider,
) -> tuple[tuple[int, ...], dict[str, Any]]:
    values: dict[str, list[list[dict[str, Any]]]] = {name: [] for name in signals}
    pieces = []
    escaped = context["id"].replace("~", "~0").replace("/", "~1")
    for index, point in enumerate(_pieces(context, year, engine)):
        graph = _graph(context, point, engine)
        hits = provider(context, graph)
        base = f"/{year}/{escaped}/pieces/{index}"
        pieces.append(
            {
                "sample_at": point.isoformat() + "+08:00",
                "data": {"p8": {"time_interactions": graph}},
            }
        )
        for signal in signals:
            values[signal].append(
                _bind_evidence(_signal(signal, graph, hits), graph, base)
            )
    vector = tuple(int(all(values[signal])) for signal in signals)
    evidence = {
        signal: {
            "present_in_all_year_pieces": bool(vector[index]),
            "pieces": values[signal],
            "method": "intersection_of_annual_boundary_pieces",
        }
        for index, signal in enumerate(signals)
    }
    return vector, {"signals": evidence, "pieces": pieces}


def _bind_evidence(
    references: list[dict[str, Any]], graph: dict[str, Any], base: str
) -> list[dict[str, Any]]:
    bound = []
    for reference in references:
        item = dict(reference)
        paths = item.pop("paths", [])
        if item["kind"] == "calculation":
            collection, key = (
                ("nodes", "node_id")
                if "node_id" in item
                else ("relations", "relation_id")
            )
            paths = [
                f"/data/p8/time_interactions/{collection}/{index}"
                for index, row in enumerate(graph[collection])
                if row["id"] == item[key]
            ]
        if any(not path.startswith("/data/p8/time_interactions/") for path in paths):
            raise ValueError("annual_rule_reference_must_bind_to_annual_graph")
        bound.append(
            dict(
                item,
                evidence_paths=[base + path for path in paths],
                alias_status="unregistered_mainline_alias_required",
            )
        )
    return bound


def _validate_scope(
    contexts: list[dict[str, Any]], scope: tuple[str, str, int], as_of_year: int
) -> None:
    if len(contexts) < 2:
        raise ValueError("need_multiple_real_candidate_contexts")
    for context in contexts:
        actual = (
            context.get("owner_user_id"),
            context.get("subject_id"),
            context.get("revision"),
        )
        if actual != scope:
            raise ValueError("candidate_context_scope_mismatch")
    cutoffs = {context.get("as_of_date") for context in contexts}
    if len(cutoffs) != 1:
        raise ValueError("candidate_source_clock_cutoffs_must_match")
    cutoff = next(iter(cutoffs))
    if cutoff is not None and date.fromisoformat(cutoff).year != as_of_year:
        raise ValueError("source_clock_year_and_cache_asof_year_mismatch")


def precompute(
    contexts: list[dict[str, Any]],
    *,
    birth_year: int,
    as_of_year: int,
    scope: tuple[str, str, int],
    rule_provider: RuleProvider | None = None,
) -> AnnualSignalCache:
    _validate_scope(contexts, scope, as_of_year)
    engine = load_engine("bazi")
    signals = tuple(
        sorted(
            {
                row["signal"]
                for items in rules()["event_rules"].values()
                for row in items
            }
        )
    )
    years = tuple(range(birth_year + 6, as_of_year + 1))
    values, evidence = [], {}
    for year in years:
        annual = [
            _year_vector(context, year, signals, engine, rule_provider or _rule_hits)
            for context in contexts
        ]
        values.append(tuple(item[0] for item in annual))
        evidence[str(year)] = {
            context["id"]: item[1]
            for context, item in zip(contexts, annual, strict=True)
        }
    columns = {
        row["id"]: {
            key: row.get(key)
            for key in (
                "label",
                "pillars",
                "time_basis",
                "engine_versions",
                "ziwei_column",
                "as_of_date",
                "source_clock",
            )
        }
        for row in contexts
    }
    return AnnualSignalCache(
        tuple(row["id"] for row in contexts),
        years,
        signals,
        tuple(values),
        canonical(columns),
        canonical(evidence),
        scope,
        *rules_identity(),
        birth_year,
        as_of_year,
        "real_charts_U2_U12_precompute_no_model_calls",
    )


def event_evidence(
    cache: AnnualSignalCache,
    candidate: int,
    event: dict[str, Any],
    cache_hash: str | None = None,
) -> dict[str, Any]:
    index = event["year"] - cache.years[0]
    vector = cache.values[index][candidate]
    values = dict(zip(cache.signal_ids, vector, strict=True))
    supported, unsupported = [], []
    for number, rule in enumerate(rules()["event_rules"][event["type"]], 1):
        item = {
            "signal": rule["signal"],
            "weight": rule["weight"],
            "source": rule["source"],
            "note": rule["note"],
            "local_evidence_index": number,
            "alias_status": "unregistered_mainline_alias_required",
            "evidence_key": [
                str(event["year"]),
                cache.candidate_ids[candidate],
                "signals",
                rule["signal"],
            ],
        }
        (supported if values[rule["signal"]] else unsupported).append(item)
    return {
        "event_id": event["id"],
        "year": event["year"],
        "for": supported,
        "against": unsupported,
        "month_not_used_for_year_only_test": event.get("month") is not None,
        "evidence_cache_hash": cache_hash or cache.fingerprint,
    }
