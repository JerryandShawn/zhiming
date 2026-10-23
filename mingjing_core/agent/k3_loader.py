"""Load the pinned official class from local verified bytes, with no Hub lookup."""

from __future__ import annotations

import importlib.metadata
import json
import sys
import types
import uuid
from functools import partial
from pathlib import Path
from typing import Any

from .context_k3 import PinnedK3Counter
from .context_types import InputMeterUnverified
from .k3_artifacts import REVISION, read_k3_lock, verify_artifacts


def check_dependencies(requirements: list[str]) -> None:
    try:
        from packaging.requirements import Requirement

        for text in requirements:
            requirement = Requirement(text)
            if (requirement.marker is None or requirement.marker.evaluate()) and importlib.metadata.version(
                requirement.name
            ) not in requirement.specifier:
                raise InputMeterUnverified()
    except (ImportError, importlib.metadata.PackageNotFoundError, ValueError):
        raise InputMeterUnverified() from None


def _module(package: str, filename: str, source: bytes, directory: Path) -> types.ModuleType:
    name = package + "." + Path(filename).stem
    module = types.ModuleType(name)
    module.__file__, module.__package__ = str(directory / filename), package
    sys.modules[name] = module
    # Execute the already hashed bytes, never an unchecked pyc or import search.
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _official_tokenizer(verified: dict[str, bytes], directory: Path) -> Any:
    package = "_zhiming_public_k3_" + uuid.uuid4().hex
    namespace = types.ModuleType(package)
    namespace.__path__ = []
    sys.modules[package] = namespace
    try:
        _module(package, "encoding_k3.py", verified["encoding_k3.py"], directory)
        module = _module(package, "tokenization_kimi.py", verified["tokenization_kimi.py"], directory)
        from tokenizers import AddedToken

        config = json.loads(verified["tokenizer_config.json"])
        tokens = {int(key): AddedToken(**value) for key, value in config["added_tokens_decoder"].items()}
        tokenizer = module.TikTokenTokenizer(
            vocab_file=str(directory / "tiktoken.model"),
            added_tokens_decoder=tokens,
            **{key: config[key] for key in ("bos_token", "eos_token", "unk_token", "pad_token")},
            additional_special_tokens=config["additional_special_tokens"],
            clean_up_tokenization_spaces=False,
        )
        if (
            type(tokenizer) is not module.TikTokenTokenizer
            or tokenizer.encode.__func__ is not module.TikTokenTokenizer.encode
        ):
            raise InputMeterUnverified()
        return tokenizer
    finally:
        for name in (package + ".tokenization_kimi", package + ".encoding_k3", package):
            sys.modules.pop(name, None)


def load_k3_counter(artifact_dir: Path) -> PinnedK3Counter:
    """The returned live-admissible estimate does not grant model-call approval."""
    try:
        lock = read_k3_lock()
        verified = verify_artifacts(artifact_dir, lock)
        check_dependencies(lock["dependencies"])
        tokenizer = _official_tokenizer(verified, artifact_dir)
        return PinnedK3Counter(
            artifact=artifact_dir / "tiktoken.model",
            version="moonshotai/Kimi-K3@" + REVISION,
            artifact_sha256=lock["files"]["tiktoken.model"]["sha256"],
            encoder_artifact=artifact_dir / "tokenization_kimi.py",
            encoder_version="official-TikTokenTokenizer@" + REVISION,
            encoder_sha256=lock["files"]["tokenization_kimi.py"]["sha256"],
            encode=partial(tokenizer.encode, allow_special_tokens=False),
            live_admissible=True,
        )
    except (OSError, ImportError, ValueError, TypeError, KeyError, AssertionError, RuntimeError):
        raise InputMeterUnverified() from None
