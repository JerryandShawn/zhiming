"""Optional bge encoder: reads only local files; never downloads or calls a service."""

import importlib
import math
import os
from pathlib import Path

from .local_vectors import KeywordVectorizer, Vector, Vectorizer


class OnnxVectorizer:
    mode = "onnx"
    degradation = None

    def __init__(self, directory: Path) -> None:
        # The model directory is an explicit deployment dependency, not a remote model ID.
        runtime = importlib.import_module("onnxruntime")
        tokenizer_module = importlib.import_module("tokenizers")
        self._np = importlib.import_module("numpy")
        self._tokenizer = tokenizer_module.Tokenizer.from_file(str(directory / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=512)
        self._session = runtime.InferenceSession(str(directory / "model.onnx"), providers=["CPUExecutionProvider"])

    def encode(self, text: str) -> Vector:
        tokens = self._tokenizer.encode(text)
        arrays = {
            "input_ids": self._np.asarray([tokens.ids], dtype="int64"),
            "attention_mask": self._np.asarray([tokens.attention_mask], dtype="int64"),
            "token_type_ids": self._np.asarray([tokens.type_ids], dtype="int64"),
        }
        feeds = {item.name: arrays[item.name] for item in self._session.get_inputs()}
        output = self._session.run(None, feeds)[0]
        # BGE's CLS pooling, not sentence mean pooling.
        vector = output[0, 0] if len(output.shape) == 3 else output[0]
        values = [float(value) for value in vector]
        if not values or not all(math.isfinite(value) for value in values):
            raise ValueError("本地向量模型输出无效")
        norm = math.sqrt(sum(value * value for value in values))
        if not norm:
            raise ValueError("本地向量模型输出无效")
        return {str(index): value / norm for index, value in enumerate(values)}


def configured_vectorizer(path: str | None = None) -> Vectorizer:
    location = path if path is not None else os.environ.get("ZHIMING_EMBEDDING_MODEL")
    if not location:
        return KeywordVectorizer()
    directory = Path(location)
    if not directory.is_dir() or not all((directory / name).is_file() for name in ("model.onnx", "tokenizer.json")):
        return KeywordVectorizer("local_model_files_missing")
    try:
        encoder = OnnxVectorizer(directory)
        encoder.encode("本地向量模型可用性检查")
        return encoder
    except Exception:
        # ORT has multiple extension exception types; failures stay local and never leak file paths or text.
        return KeywordVectorizer("local_model_runtime_unavailable")
