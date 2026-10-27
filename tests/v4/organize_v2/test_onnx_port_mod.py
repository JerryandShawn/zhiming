"""All encoders are injected synthetic objects; no model/runtime download or load occurs."""

import traceback

import pytest

from mingjing_core.organize.v2.onnx_port import EncoderError, OnnxConfig, OnnxEncoderPort


class SyntheticEncoder:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def encode(self, texts):
        self.calls.append(texts)
        return self.output


def configured(output):
    port = OnnxEncoderPort(OnnxConfig("synthetic-only-not-a-real-model.onnx", dimension=3))
    encoder = SyntheticEncoder(output)
    assert not port.enabled
    assert port.activate(lambda path, dimension: encoder)
    return port, encoder


def test_no_path_never_touches_factory_and_returns_explicit_unavailable():
    calls = []
    port = OnnxEncoderPort()
    assert not port.activate(lambda *args: calls.append(args))
    assert port.encode(["合成文本"]) is None and not port.enabled and not calls


def test_configured_path_does_not_implicitly_activate_or_encode():
    port = OnnxEncoderPort(OnnxConfig("synthetic-path.onnx"))
    assert not port.enabled and port.encode(["合成文本"]) is None


def test_explicit_synthetic_activation_shape_and_immutable_output():
    output = [[1, 0, 0.5], [-1, 2, 0.25]]
    port, encoder = configured(output)
    result = port.encode(["合成甲", "合成乙"])
    output[0][0] = 999
    assert result == ((1.0, 0.0, 0.5), (-1.0, 2.0, 0.25))
    assert encoder.calls == [("合成甲", "合成乙")]
    port.deactivate()
    assert port.encode(["合成丙"]) is None


@pytest.mark.parametrize(
    "output",
    [
        None,
        "not-matrix",
        [[1, 2]],
        [[1, 2, 3], [4, 5, 6]],
        [[True, 2, 3]],
        [[1, float("nan"), 3]],
        [[1, float("inf"), 3]],
        [[1, "2", 3]],
        {"vector": [1, 2, 3]},
    ],
)
def test_bad_shape_dimension_and_nonfinite_fail_closed(output):
    port, encoder = configured(output)
    with pytest.raises(EncoderError, match="^encoder_output_unavailable$"):
        port.encode(["不可回显的合成私文"])
    assert not port.enabled and port.encode(["合成后续"]) is None
    assert len(encoder.calls) == 1


@pytest.mark.parametrize("texts", ["single string", None, [1], [True], {"text": "x"}])
def test_input_must_be_a_batch_of_texts(texts):
    with pytest.raises(EncoderError):
        OnnxEncoderPort().encode(texts)


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("dimension", True),
        ("dimension", 0),
        ("dimension", 65537),
        ("max_batch", 0),
        ("max_batch", True),
        ("model_path", 1),
    ],
)
def test_config_requires_typed_bounds(keyword, value):
    with pytest.raises(EncoderError):
        OnnxConfig(**{keyword: value})


def test_empty_batch_does_not_call_synthetic_encoder_and_batch_limit_applies():
    port, encoder = configured([])
    assert port.encode([]) == () and not encoder.calls
    with pytest.raises(EncoderError):
        port.encode(["x"] * 129)


def test_loader_failure_is_private_and_explicitly_unavailable():
    port = OnnxEncoderPort(OnnxConfig("synthetic-path.onnx"))

    def broken_factory(*args):
        raise OSError("合成错误私文")

    with pytest.raises(EncoderError, match="^encoder_activation_failed$"):
        port.activate(broken_factory)
    assert not port.enabled


class SyntheticRuntimeFailure(Exception):
    """Mimics provider-defined exception classes without importing any runtime."""


@pytest.mark.parametrize("boundary", ["activation", "encoding"])
def test_custom_runtime_exception_cannot_echo_path_or_private_text(boundary):
    port = OnnxEncoderPort(OnnxConfig("synthetic-local-path.onnx", dimension=3))

    def fail(*args):
        raise SyntheticRuntimeFailure("synthetic private text/path")

    encoder = SyntheticEncoder([])
    encoder.encode = fail
    if boundary == "encoding":
        port.activate(lambda *args: encoder)
    with pytest.raises(EncoderError) as caught:
        if boundary == "encoding":
            port.encode(["合成私有输入"])
        else:
            port.activate(fail)
    assert not port.enabled
    assert "synthetic private text/path" not in str(caught.value)
    assert "synthetic private text/path" not in repr(caught.value)
    assert "SyntheticRuntimeFailure" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("failure", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("boundary", ["activation", "encoding"])
def test_process_control_base_exceptions_are_not_swallowed(failure, boundary):
    port = OnnxEncoderPort(OnnxConfig("synthetic-local-path.onnx", dimension=3))

    def stop(*args):
        raise failure()

    if boundary == "encoding":
        encoder = SyntheticEncoder([])
        encoder.encode = stop
        port.activate(lambda *args: encoder)
    with pytest.raises(failure):
        if boundary == "encoding":
            port.encode(["合成输入"])
        else:
            port.activate(stop)


def test_disabled_encoder_leaves_pure_lexical_classifier_available():
    from mingjing_core.organize.v2.classifier import LocalClassifier

    port = OnnxEncoderPort()
    assert port.encode(["这周要准备求职面试和投递简历。"]) is None
    assert LocalClassifier().classify("这周要准备求职面试和投递简历。").area_id == "career"
