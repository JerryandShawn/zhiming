"""Separate reviewed source-backfill inputs; pins never reconstruct source authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.first_release_contracts import digest, ordinary, require
from tools.first_release_incremental import file_hash
from tools.first_release_incremental_forward import ForwardInputs
from tools.first_release_source_process import SourceReplayPin, _digest

ROOT = Path(__file__).parent.parent
DIRECT = frozenset(
    "tools/" + name
    for name in (
        "first_release_source_backfill_pin.py",
        "first_release_source_backfill_process.py",
        "first_release_source_backfill_worker.py",
        "first_release_backfill_effects.py",
        "first_release_backfill_expected.py",
    )
)


def controls(request: ForwardInputs, replay_pin: SourceReplayPin) -> dict[str, str]:
    replay_pin.validate(request)
    return _merged_controls(replay_pin)


def _merged_controls(replay_pin: SourceReplayPin) -> dict[str, str]:
    """Callers validate the replay pin in this invocation before merging current hashes."""
    result = dict(replay_pin.controls)
    for name in DIRECT:
        sha = file_hash(ROOT / name)
        require(name not in result or result[name] == sha, "SOURCE_BACKFILL_INHERITED_CONTROL_MISMATCH")
        result[name] = sha
    return result


@dataclass(frozen=True)
class SourceBackfillPin:
    binding_sha256: str
    forward_pin_sha256: str
    replay_pin_sha256: str
    candidate: str
    manifest_sha256: str
    locks: tuple[tuple[str, str], ...]
    ledger_sha256: str
    python_sha256: str
    controls: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> SourceBackfillPin:
        names = set(cls.__dataclass_fields__)
        require(
            type(value) is dict
            and set(value) == names | {"schema"}
            and value["schema"] == "first-release-local-source-backfill-pin-v1"
            and type(value["controls"]) is dict
            and type(value["locks"]) is dict,
            "SOURCE_BACKFILL_PIN_FIELDS",
        )
        return cls(
            **{name: value[name] for name in names - {"controls", "locks"}},
            controls=tuple(sorted(value["controls"].items())),
            locks=tuple(sorted(value["locks"].items())),
        )

    def validate(self, request: ForwardInputs, replay_pin: SourceReplayPin) -> None:
        require(
            type(self) is SourceBackfillPin and type(request) is ForwardInputs and type(replay_pin) is SourceReplayPin,
            "SOURCE_BACKFILL_TYPED_PIN",
        )
        replay_pin.validate(request)
        require(
            all(digest(getattr(self, name)) for name in self.__dataclass_fields__ if name.endswith("sha256"))
            and digest(self.candidate, 40),
            "SOURCE_BACKFILL_PIN_DIGEST",
        )
        require(
            type(self.controls) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.controls)
            and self.controls == tuple(sorted(_merged_controls(replay_pin).items()))
            and type(self.locks) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.locks)
            and self.locks == tuple(sorted(request.source.release.locks)),
            "SOURCE_BACKFILL_CONTROL_SET",
        )
        require(
            (
                self.binding_sha256,
                self.forward_pin_sha256,
                self.replay_pin_sha256,
                self.candidate,
                self.manifest_sha256,
                self.python_sha256,
                self.ledger_sha256,
            )
            == (
                request.pin.binding_sha256,
                _digest(asdict(request.pin)),
                _digest(asdict(replay_pin)),
                request.source.release.candidate,
                request.source.release.manifest_sha256,
                request.source.python_sha256,
                request.capture.pin.ledger_sha256,
            ),
            "SOURCE_BACKFILL_REVIEW_BINDING",
        )
        ledger = request.source.operation_dir / "latest-withdrawals.json"
        for path, sha in [(ROOT / name, sha) for name, sha in self.controls] + [(ledger, self.ledger_sha256)]:
            ordinary(path)
            require(digest(sha) and file_hash(path) == sha, "SOURCE_BACKFILL_REVIEWED_FILE_CHANGED")
