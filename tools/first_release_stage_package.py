"""Canonical Git bundle and exclusive unpack for F's independent stage release."""

from __future__ import annotations

import json
import os
import re
from argparse import Namespace
from pathlib import Path

from tools.deploy_core import bundle
from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_restore import SafeParser
from tools.first_release_stage_unpack import unpack


def make_bundle(source: Path, candidate: str, artifact: Path) -> dict:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", candidate)), "STAGE_PACKAGE_CANDIDATE")
    ordinary(source, directory=True)
    ordinary(artifact.parent, directory=True)
    descriptor = os.open(artifact, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(descriptor)
    # Existing canonical Git-blob packaging includes tracked files only. A failed
    # package is retained at this exclusively reserved path, never overwritten.
    return bundle(Namespace(source=str(source), commit=candidate, artifact=str(artifact)))


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("bundle", "unpack"))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--local-drill", action="store_true")
    parser.add_argument("--apply", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.action == "bundle":
            require(args.source is not None, "STAGE_PACKAGE_SOURCE_REQUIRED")
            result = make_bundle(args.source, args.candidate, args.artifact)
        else:
            require(args.release is not None and args.artifact_sha256 is not None, "STAGE_PACKAGE_UNPACK_ARGUMENTS")
            if not args.apply:
                print(json.dumps({"status": "arguments_validated", "files_written": 0}))
                return 0
            result = unpack(
                args.artifact, args.artifact_sha256, args.candidate, args.release, local_drill=args.local_drill
            )
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "STAGE_PACKAGE_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
