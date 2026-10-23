"""Optional encoder port only: no runtime import, filesystem read, download or implicit activation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from threading import RLock
from typing import Protocol


class EncoderError(ValueError):
    """Fixed machine reason without the input text, model output or local path."""


@dataclass(frozen=True)
class OnnxConfig:
    model_path: str | None = None
    dimension: int = 384
    max_batch: int = 128

    def __post_init__(self) -> None:
        if self.model_path is not None and type(self.model_path) is not str:
            raise EncoderError("encoder_path_invalid")
        if self.model_path is not None and not self.model_path.strip():
            object.__setattr__(self, "model_path", None)
        if type(self.dimension) is not int or not 1 <= self.dimension <= 65536:
            raise EncoderError("encoder_dimension_invalid")
        if type(self.max_batch) is not int or not 1 <= self.max_batch <= 512:
            raise EncoderError("encoder_batch_limit_invalid")


class BatchEncoder(Protocol):
    def encode(self, texts: tuple[str, ...]) -> Sequence[Sequence[float]]:
        """A host adapter converts runtime tensors to Python sequences; no runtime is bundled here."""
        ...


class EncoderFactory(Protocol):
    def __call__(self, model_path: str, dimension: int) -> BatchEncoder:
        """Only an explicit host activate call grants access to a configured local encoder."""
        ...


class OnnxEncoderPort:
    def __init__(self, config: OnnxConfig | None = None) -> None:
        if config is not None and not isinstance(config, OnnxConfig):
            raise EncoderError("encoder_config_required")
        self._config = config or OnnxConfig()
        self._encoder: BatchEncoder | None = None
        self._lock = RLock()

    @property
    def config(self) -> OnnxConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._encoder is not None

    def activate(self, factory: EncoderFactory) -> bool:
        with self._lock:
            if self.config.model_path is None:
                return False
            if not callable(factory):
                raise EncoderError("encoder_explicit_factory_required")
            try:
                encoder = factory(self.config.model_path, self.config.dimension)
            except Exception:
                self._encoder = None
                raise EncoderError("encoder_activation_failed") from None
            if not callable(getattr(encoder, "encode", None)):
                self._encoder = None
                raise EncoderError("encoder_factory_contract_invalid")
            self._encoder = encoder
            return True

    def deactivate(self) -> None:
        with self._lock:
            self._encoder = None

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...] | None:
        if not isinstance(texts, (tuple, list)):
            raise EncoderError("encoder_text_batch_invalid")
        batch = tuple(texts)
        if any(type(text) is not str for text in batch):
            raise EncoderError("encoder_text_batch_invalid")
        if len(batch) > self.config.max_batch:
            raise EncoderError("encoder_text_batch_too_large")
        with self._lock:
            if self._encoder is None:
                return None
            if not batch:
                return ()
            try:
                result = self._encoder.encode(batch)
                return _vectors(result, len(batch), self.config.dimension)
            except Exception:
                self._encoder = None
                raise EncoderError("encoder_output_unavailable") from None


def _vectors(result: object, count: int, dimension: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(result, (tuple, list)) or len(result) != count:
        raise EncoderError("encoder_output_shape_invalid")
    vectors = []
    for row in result:
        if not isinstance(row, (tuple, list)) or len(row) != dimension:
            raise EncoderError("encoder_output_dimension_invalid")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in row):
            raise EncoderError("encoder_output_non_finite")
        vectors.append(tuple(float(value) for value in row))
    return tuple(vectors)
