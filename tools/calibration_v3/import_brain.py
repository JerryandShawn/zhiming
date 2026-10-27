"""Strict parser for design 25; returned full texts and labels must stay in private storage."""

import hashlib
import re

from .models import SECTION_ITEMS, CalibrationError, PrivateDataset, PrivateSample, label_vector


def _field(block: str, name: str) -> str:
    match = re.search(r"^- \*\*" + re.escape(name) + r"\*\*：(.*?)(?=\n- \*\*|\Z)", block, re.M | re.S)
    if match is None or not match.group(1).strip():
        raise CalibrationError("brain_sample_field_missing")
    return match.group(1).strip()


def _summary(text: str) -> dict[str, list[str]]:
    try:
        table = text.split("## 16 ·", 1)[1].split("## 17 ·", 1)[0]
    except IndexError:
        raise CalibrationError("brain_summary_missing") from None
    rows = {}
    for line in table.splitlines():
        parts = [value.strip() for value in line.strip().strip("|").split("|")]
        if len(parts) != 8 or re.fullmatch(r"(?:[1-9]|1[0-5])-(?:R[12]|P[12]|T)", parts[0]) is None:
            continue
        if parts[0] in rows:
            raise CalibrationError("brain_summary_duplicate")
        rows[parts[0]] = parts
    if len(rows) != 75:
        raise CalibrationError("brain_summary_count_invalid")
    return rows


def _sample(source_id: str, block: str, row: list[str]) -> PrivateSample:
    section = int(source_id.split("-", 1)[0])
    item = SECTION_ITEMS[section - 1]
    if row[2] != item or row[3] not in {"R", "P", "T"}:
        raise CalibrationError("brain_summary_item_mismatch")
    summary_verdict = row[4]
    body_verdict = _field(block, "正确判定")
    violation = summary_verdict in {"revise", "违反（只记录）"}
    if summary_verdict not in {"pass", "revise", "违反（只记录）"} or (
        body_verdict.startswith(("revise", "违反")) != violation
    ):
        raise CalibrationError("brain_summary_verdict_mismatch")
    number = re.match(r"[1-5]", row[5])
    if number is None or not _field(block, "严重度").startswith(number.group()):
        raise CalibrationError("brain_summary_severity_mismatch")
    draft_lines = _field(block, "明镜初稿").splitlines()
    if any(line.strip() and not line.lstrip().startswith(">") for line in draft_lines):
        raise CalibrationError("brain_draft_format_invalid")
    labels = {name: name == item and violation for name in SECTION_ITEMS}
    return PrivateSample(
        source_id,
        item,
        _field(block, "材料"),
        _field(block, "用户"),
        "\n".join(re.sub(r"^\s*> ?", "", line) for line in draft_lines).strip(),
        label_vector(labels),
        int(number.group()),
        row[6] == "✓",
        row[7] == "✓",
        row[3],
        _field(block, "判定理由"),
    )


def parse_brain_document(raw: bytes) -> PrivateDataset:
    if type(raw) is not bytes:
        raise CalibrationError("brain_utf8_bytes_required")
    try:
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeError:
        raise CalibrationError("brain_utf8_invalid") from None
    rows = _summary(text)
    headings = list(re.finditer(r"^#### ((?:[1-9]|1[0-5])-(?:R[12]|P[12]|T)) · .+$", text, re.M))
    if len(headings) != 75 or {match.group(1) for match in headings} != set(rows):
        raise CalibrationError("brain_sample_count_invalid")
    samples = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else text.index("## 16 ·")
        samples.append(_sample(match.group(1), text[match.end() : end].split("\n---", 1)[0], rows[match.group(1)]))
    try:
        common = text.split("### 0.4", 1)[1].split("\n## 1 ·", 1)[0].rstrip("-\n ")
    except IndexError:
        raise CalibrationError("brain_common_context_missing") from None
    if sum(sample.uncertain for sample in samples) != 6 or sum(sample.j02 for sample in samples) != 20:
        raise CalibrationError("brain_annotation_count_invalid")
    return PrivateDataset(hashlib.sha256(raw).hexdigest(), common, tuple(samples))
