"""Long lexical indexing is bounded while ordinary token behavior stays unchanged."""

import importlib
import re

import pytest

module = importlib.import_module("mingjing_core.memory.tokenize")


@pytest.mark.parametrize(
    "text",
    [
        "日主喜用神和流年",
        "夜班、考研与工作",
        "MixedCase 2026-10-17",
        "我喜欢蓝杯，不要保存秘密。",
        "\n。 ，",
        "龘靐齉爩",
    ],
)
def test_ordinary_text_keeps_exact_existing_jieba_tokens(text):
    expected = list(
        dict.fromkeys(word.lower() for word in module.tokenizer().cut(text) if re.search(r"[\w\u3400-\u9fff]", word))
    )
    assert module.tokenize(text) == expected


def test_huge_unknown_run_never_reaches_jieba_as_one_hmm_problem(monkeypatch):
    original, sizes = module.tokenizer(), []

    class ObservedTokenizer:
        def cut(self, text):
            sizes.append(len(text))
            return original.cut(text)

    monkeypatch.setattr(module, "tokenizer", lambda: ObservedTokenizer())
    result = module.tokenize("龘靐齉爩" * 45250)
    assert result and max(sizes) <= 512
    assert sum(sizes) >= 181000


def test_overlap_keeps_known_terms_at_window_boundaries():
    text = "龘" * 510 + "喜用神" + "龘" * 4300
    assert "喜用神" in module.tokenize(text)


def test_long_punctuated_text_keeps_existing_tokens_and_private_data_never_indexes(monkeypatch):
    text = "日主喜用神，夜班考研。" * 1000
    expected = list(
        dict.fromkeys(word.lower() for word in module.tokenizer().cut(text) if re.search(r"[\w\u3400-\u9fff]", word))
    )
    assert module.tokenize(text) == expected

    def forbidden(*args):
        pytest.fail("Private originals must not enter lexical indexing")

    monkeypatch.setattr(module, "tokenizer", forbidden)
    assert module.searchable_data("message", dict(content=text, incognito=True))["search_tokens"] == ""
