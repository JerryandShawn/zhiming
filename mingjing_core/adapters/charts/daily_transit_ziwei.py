"""Actual installed horoscope layers linked to actual natal star locations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .daily_transit_natal import PreparedNatal
from .worker import iztro_provenance, version
from .ziwei_flying import palace_flying_transformations

LAYERS = ("yearly", "monthly", "daily")
ZIWEI_SOURCE = {
    "title": "安装py-iztro运限与本命星曜映射",
    "url": "https://docs.iztro.com/posts/horoscope",
    "status": "installed_library_convention_not_independent_school_validation",
}


def _rebase(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("/data/palaces/"):
            return value.replace("/data/palaces/", "/data/ziwei/natal/palaces/", 1)
        if value.startswith("/data/horoscope/"):
            return value.replace("/data/horoscope/", "/data/ziwei/horoscope/", 1)
        return value
    if isinstance(value, list):
        return [_rebase(item) for item in value]
    if isinstance(value, dict):
        return {key: _rebase(item) for key, item in value.items()}
    return value


def ziwei_day(prepared: PreparedNatal, day: str) -> dict[str, Any]:
    # Both arguments are explicit: upstream defaults otherwise read current time.
    horoscope = prepared.ziwei_ast.horoscope(day, 6)
    native = deepcopy(prepared.ziwei_natal)
    native["horoscope"] = {
        "target_date": day,
        "snapshot_time_index": 6,
        "lunar": horoscope.lunar_date,
        **{
            layer: prepared.ziwei_engine.scope(getattr(horoscope, layer))
            for layer in LAYERS
        },
    }
    flying = palace_flying_transformations(native)
    return {
        "school": flying["school"],
        "versions": {
            "py-iztro": version("py-iztro"),
            "pythonmonkey": version("pythonmonkey"),
            **iztro_provenance(),
        },
        "natal": deepcopy(prepared.ziwei_natal),
        "horoscope": native["horoscope"],
        "transformations": _rebase(
            {layer: flying["temporal_layers"][layer] for layer in LAYERS}
        ),
        "source_refs": flying["source_refs"],
        "table_sha256": flying["table_sha256"],
        "limits": flying["limits"],
    }


def ziwei_hits(data: dict[str, Any]) -> list[dict[str, Any]]:
    hits = []
    for layer in LAYERS:
        for index, link in enumerate(data["transformations"][layer]["links"]):
            if link["status"] != "resolved":
                continue
            location = link["locations"][0]
            hits.append(
                {
                    "rule_id": f"daily.ziwei.{layer}.{index}",
                    "met": True,
                    "school": data["school"],
                    "source": ZIWEI_SOURCE,
                    "context": {
                        "system": "ziwei",
                        "kind": "mutagen",
                        "layer": layer,
                        "mutagen": link["mutagen"],
                        "natal_palace": location["natal_palace"],
                        "palace_index": location["palace_index"],
                    },
                    "evidence_paths": list(link["evidence_paths"]),
                }
            )
    return hits
