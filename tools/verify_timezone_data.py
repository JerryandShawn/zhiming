"""Offline package-data parity check, isolated from chart algorithms and runtime defaults.

Python normally searches system TZPATH before falling back to tzdata. This tool
temporarily disables those paths and clears caches before using ZoneInfo, then
restores the caller's paths. Run it in its own process; it is not a runtime hook.
References: https://docs.python.org/3.11/library/zoneinfo.html#data-sources
and https://pypi.org/pypi/tzdata/2026.5/json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import re
import sys
import zoneinfo
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata, resources
from pathlib import Path

import tzdata

EXPECTED_VERSION = "2026.5"
EXPECTED_IANA = "2026e"
EXPECTED_DIGEST = "f66f063a04cb9fb1a5238bac645d1aaea32957502bd3bb782c670ac5df578df2"
ARTIFACT_HASHES = frozenset(
    {
        "8cc73c0a0bfca7dbfa59235d60b2eff82231dee33f53d206db1acd9173cfc0a7",
        "b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac",
    }
)
ZONE_HASHES = {
    "America/New_York": "d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9",
    "Asia/Kathmandu": "76b8f1bfe072231a1d9e7f8501310e27c0d08048c48f7422860b6477c142c438",
    "Asia/Shanghai": "bf8b7ed82fe6e63e6d98f8cea934eeac901cd16aba85eb5755ce3f8b4289ea8a",
    "Australia/Lord_Howe": "f368bd25659c0293d02bb79ec7dac7d5b73a92dffafce14b4dd2ffb8ba11aada",
    "Europe/London": "676541f0b8ad457c744c093f807589adcad909e3fd03f901787d08786eedbd33",
    "Pacific/Apia": "dc70c47c80ab2c87a1ab754bab8febfc38508059e249dfe55e73a3759808ea14",
}


class TimezoneVerificationError(RuntimeError):
    """A lock, package or observed rule differs from the fixed timezone baseline."""


@dataclass(frozen=True)
class Case:
    name: str
    zone: str
    utc: str
    local: str
    fold: int = 0
    dst_seconds: int = 0


# These include civil-time gaps, repeated times, a non-hour DST shift and a skipped date.
CASES = (
    Case("shanghai-current", "Asia/Shanghai", "2026-10-17T00:00:00+00:00", "2026-10-17T08:00:00+08:00"),
    Case("shanghai-1986-before", "Asia/Shanghai", "1986-05-03T17:59:59+00:00", "1986-05-04T01:59:59+08:00"),
    Case("shanghai-1986-after", "Asia/Shanghai", "1986-05-03T18:00:00+00:00", "1986-05-04T03:00:00+09:00", 0, 3600),
    Case("shanghai-1991-fold0", "Asia/Shanghai", "1991-09-14T16:30:00+00:00", "1991-09-15T01:30:00+09:00", 0, 3600),
    Case("shanghai-1991-fold1", "Asia/Shanghai", "1991-09-14T17:30:00+00:00", "1991-09-15T01:30:00+08:00", 1),
    Case("new-york-spring-before", "America/New_York", "2026-03-08T06:59:59+00:00", "2026-03-08T01:59:59-05:00"),
    Case(
        "new-york-spring-after", "America/New_York", "2026-03-08T07:00:00+00:00", "2026-03-08T03:00:00-04:00", 0, 3600
    ),
    Case("new-york-fold0", "America/New_York", "2026-11-01T05:30:00+00:00", "2026-11-01T01:30:00-04:00", 0, 3600),
    Case("new-york-fold1", "America/New_York", "2026-11-01T06:30:00+00:00", "2026-11-01T01:30:00-05:00", 1),
    Case("london-spring-before", "Europe/London", "2026-03-29T00:59:59+00:00", "2026-03-29T00:59:59+00:00"),
    Case("london-spring-after", "Europe/London", "2026-03-29T01:00:00+00:00", "2026-03-29T02:00:00+01:00", 0, 3600),
    Case("london-fold0", "Europe/London", "2026-10-25T00:30:00+00:00", "2026-10-25T01:30:00+01:00", 0, 3600),
    Case("london-fold1", "Europe/London", "2026-10-25T01:30:00+00:00", "2026-10-25T01:30:00+00:00", 1),
    Case("kathmandu-before", "Asia/Kathmandu", "1985-12-31T18:29:59+00:00", "1985-12-31T23:59:59+05:30"),
    Case("kathmandu-after", "Asia/Kathmandu", "1985-12-31T18:30:00+00:00", "1986-01-01T00:15:00+05:45"),
    Case("apia-before", "Pacific/Apia", "2011-12-30T09:59:59+00:00", "2011-12-29T23:59:59-10:00", 0, 3600),
    Case("apia-after", "Pacific/Apia", "2011-12-30T10:00:00+00:00", "2011-12-31T00:00:00+14:00", 0, 3600),
    Case("lord-howe-spring-before", "Australia/Lord_Howe", "2026-10-03T15:29:59+00:00", "2026-10-04T01:59:59+10:30"),
    Case(
        "lord-howe-spring-after",
        "Australia/Lord_Howe",
        "2026-10-03T15:30:00+00:00",
        "2026-10-04T02:30:00+11:00",
        0,
        1800,
    ),
    Case("lord-howe-fold0", "Australia/Lord_Howe", "2026-04-04T14:45:00+00:00", "2026-04-05T01:45:00+11:00", 0, 1800),
    Case("lord-howe-fold1", "Australia/Lord_Howe", "2026-04-04T15:15:00+00:00", "2026-04-05T01:45:00+10:30", 1),
)


def lock_entry(text: str) -> tuple[str, frozenset[str]]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("tzdata==")]
    if len(starts) != 1:
        raise TimezoneVerificationError("Expected exactly one tzdata lock entry")
    start = starts[0]
    version = lines[start].removeprefix("tzdata==").removesuffix("\\").strip()
    end = start + 1
    while end < len(lines) and (not lines[end] or lines[end][0].isspace() or lines[end].startswith("#")):
        end += 1
    hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", "\n".join(lines[start:end]))
    return version, frozenset(hashes)


def verify_locks(repo: Path) -> dict[str, str]:
    versions = {}
    for name in ("requirements-core.lock", "requirements-charts.lock", "tools/timezone/tzdata.lock"):
        text = (repo / name).read_text(encoding="utf-8")
        version, hashes = lock_entry(text)
        if version != EXPECTED_VERSION:
            raise TimezoneVerificationError(f"Unexpected tzdata pin in {name}")
        if name != "requirements-charts.lock" and hashes != ARTIFACT_HASHES:
            raise TimezoneVerificationError(f"Unexpected tzdata artifact hashes in {name}")
        if name.startswith("tools/"):
            dependencies = [line for line in text.splitlines() if line and not line.startswith(("#", " ", "\t"))]
            if len(dependencies) != 1:
                raise TimezoneVerificationError("Timezone-only lock must contain exactly one dependency")
        versions[name] = version
    return versions


@contextmanager
def packaged_zoneinfo() -> Iterator[None]:
    previous = zoneinfo.TZPATH
    zoneinfo.reset_tzpath(())
    zoneinfo.ZoneInfo.clear_cache()
    try:
        yield
    finally:
        zoneinfo.reset_tzpath(previous)
        zoneinfo.ZoneInfo.clear_cache()


def case_record(case: Case, value: datetime) -> dict[str, str | int]:
    dst = value.dst()
    if dst is None:
        raise TimezoneVerificationError(f"Missing DST offset for {case.name}")
    return {
        "id": case.name,
        "zone": case.zone,
        "utc": case.utc,
        "local": value.isoformat(timespec="seconds"),
        "fold": value.fold,
        "dst_seconds": int(dst.total_seconds()),
    }


def check_case(case: Case, data: bytes) -> dict[str, str | int]:
    utc = datetime.fromisoformat(case.utc)
    observed = case_record(case, utc.astimezone(zoneinfo.ZoneInfo(case.zone)))
    if (observed["local"], observed["fold"], observed["dst_seconds"]) != (case.local, case.fold, case.dst_seconds):
        raise TimezoneVerificationError(f"Timezone boundary differs: {case.name}")
    direct = zoneinfo.ZoneInfo.from_file(io.BytesIO(data), key=case.zone)
    if case_record(case, utc.astimezone(direct)) != observed:
        raise TimezoneVerificationError(f"ZoneInfo differs from packaged TZif: {case.name}")
    return observed


def snapshot() -> dict[str, object]:
    if (metadata.version("tzdata"), tzdata.__version__, tzdata.IANA_VERSION) != (
        EXPECTED_VERSION,
        EXPECTED_VERSION,
        EXPECTED_IANA,
    ):
        raise TimezoneVerificationError("Installed tzdata distribution/module/IANA version differs")
    root = resources.files("tzdata.zoneinfo")
    zi_version = root.joinpath("tzdata.zi").read_text(encoding="utf-8").splitlines()[0].removeprefix("# version ")
    if zi_version != EXPECTED_IANA:
        raise TimezoneVerificationError("Packaged tzdata.zi IANA version differs")
    data = {zone: root.joinpath(*zone.split("/")).read_bytes() for zone in ZONE_HASHES}
    hashes = {zone: hashlib.sha256(content).hexdigest() for zone, content in data.items()}
    if hashes != ZONE_HASHES:
        raise TimezoneVerificationError("Packaged timezone TZif bytes differ")
    with packaged_zoneinfo():
        records = [check_case(case, data[case.zone]) for case in CASES]
        paths = list(zoneinfo.TZPATH)
    return {
        "distribution_version": EXPECTED_VERSION,
        "iana_version": EXPECTED_IANA,
        "tzdata_zi_version": zi_version,
        "data_source": "tzdata-package",
        "constructor": "zoneinfo.ZoneInfo",
        "tzpath": paths,
        "zone_sha256": hashes,
        "cases": records,
    }


def digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def verify(repo: Path) -> dict[str, object]:
    versions = verify_locks(repo)
    observed = snapshot()
    observed_digest = digest(observed)
    if observed_digest != EXPECTED_DIGEST:
        raise TimezoneVerificationError("Timezone boundary/data digest differs from the fixed baseline")
    return {
        "snapshot": observed,
        "sha256": observed_digest,
        "lock_versions": versions,
        "artifact_sha256": sorted(ARTIFACT_HASHES),
        "runtime": {"platform": sys.platform, "python": platform.python_version()},
        "scope": "Offline timezone package data only; excludes full Charts dependencies and chart algorithms.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.repo)
    except (TimezoneVerificationError, OSError, metadata.PackageNotFoundError) as error:
        print(f"Timezone verification failed: {error}", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"tzdata {EXPECTED_VERSION} / IANA {EXPECTED_IANA}: {len(CASES)} cases, SHA256 {report['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
