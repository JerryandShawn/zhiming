"""Source-shape parser tests with invented protocol text, never the actual 75 hard cases."""

import pytest

from tools.calibration_v3.import_brain import parse_brain_document
from tools.calibration_v3.models import ITEMS, SECTION_ITEMS, CalibrationError


def toy_document() -> bytes:
    blocks = ["### 0.4 Shared\n协议测试材料，不是25号难例。\n"]
    rows = []
    for number, item in enumerate(SECTION_ITEMS, 1):
        for suffix in ("R1", "R2", "P1", "P2", "T"):
            sample_id = f"{number}-{suffix}"
            verdict = "revise" if suffix.startswith("R") else "pass"
            blocks.append(
                f"#### {sample_id} · protocol-only\n- **材料**：toy material\n- **用户**：toy user\n"
                f"- **明镜初稿**：\n  > TOY_PARSER_BODY\n- **正确判定**：{verdict}\n"
                "- **判定理由**：toy protocol rationale\n- **严重度**：2\n\n---\n"
            )
            uncertain = "✓" if number <= 6 and suffix == "T" else ""
            j02 = "✓" if number <= 4 else ""
            rows.append(f"| {sample_id} | protocol | {item} | {suffix[0]} | {verdict} | 2 | {uncertain} | {j02} |")
    blocks.append("## 16 · 汇总\n" + "\n".join(rows) + "\n## 17 · Flow\n")
    return "\n".join(blocks).encode("utf-8")


def test_source_parser_retains_full_private_content_and_explicit_brain_origin() -> None:
    parsed = parse_brain_document(toy_document())
    assert len(parsed.samples) == 75 and parsed.provenance == "brain_ai"
    assert all(len(sample.labels) == 15 and set(dict(sample.labels)) == set(ITEMS) for sample in parsed.samples)
    assert sum(sample.uncertain for sample in parsed.samples) == 6
    assert sum(sample.j02 for sample in parsed.samples) == 20
    assert "TOY_PARSER_BODY" not in repr(parsed)
    assert all("TOY_PARSER_BODY" not in repr(sample) for sample in parsed.samples)


@pytest.mark.parametrize(
    "change", ["missing-block", "duplicate-row", "wrong-item", "mismatched-verdict", "missing-field"]
)
def test_source_disagreement_or_missing_fields_is_not_silently_imported_as_gold(change: str) -> None:
    raw = toy_document().decode("utf-8")
    if change == "missing-block":
        raw = raw.replace("#### 1-R1 ·", "#### invalid ·", 1)
    elif change == "duplicate-row":
        raw = raw.replace("## 17 ·", "| 1-R1 | protocol | J5 | R | revise | 2 | | ✓ |\n## 17 ·", 1)
    elif change == "wrong-item":
        raw = raw.replace("| 1-R1 | protocol | J5 |", "| 1-R1 | protocol | E1 |", 1)
    elif change == "mismatched-verdict":
        raw = raw.replace("- **正确判定**：revise", "- **正确判定**：pass", 1)
    else:
        raw = raw.replace("- **用户**：toy user", "- **缺失**：toy user", 1)
    with pytest.raises(CalibrationError) as caught:
        parse_brain_document(raw.encode("utf-8"))
    assert "TOY_PARSER_BODY" not in str(caught.value)


@pytest.mark.parametrize("raw", [b"\xff", b"", "not bytes"])
def test_non_utf8_or_non_document_input_is_a_controlled_error(raw: object) -> None:
    with pytest.raises(CalibrationError):
        parse_brain_document(raw)
