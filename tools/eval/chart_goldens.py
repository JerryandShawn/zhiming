"""Structural chart checks and engine-derived synthetic interval observations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

FIXTURE = Path(__file__).parent / "fixtures" / "c06_ziwei_golden.yaml"
HOURS = "子丑寅卯辰巳午未申酉戌亥子"


class Sample(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    civil_datetime: str
    corrected_time: str
    hour_index: int = Field(ge=0, le=12)
    ming_gong: str
    palace_ganzhi: str
    major_stars: list[str]


class Branch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    hour_index: int = Field(ge=0, le=12)
    label: str
    major_stars: list[str]


class ChartGolden(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["c06-ziwei-golden-v1"]
    scenario_id: Literal["C06"]
    synthetic: Literal[True]
    input: dict[str, Any]
    sampling: dict[str, Any]
    versions: dict[str, Any]
    samples: list[Sample] = Field(min_length=1)
    boundary_probes: list[Sample]
    branches: list[Branch] = Field(min_length=1)
    sampled_stable: bool
    external_cross_check: Literal["deferred_to_P8"]

    @model_validator(mode="after")
    def consistent_observations(self) -> ChartGolden:
        values = {tuple(sorted(sample.major_stars)) for sample in self.samples}
        if self.sampled_stable != (len(values) == 1):
            raise ValueError("Golden stability must be derived from calculated samples")
        expected = {(sample.hour_index, tuple(sample.major_stars)) for sample in self.samples}
        actual = {(branch.hour_index, tuple(branch.major_stars)) for branch in self.branches}
        if expected != actual:
            raise ValueError("Golden branches must exactly cover the calculated samples")
        for branch in self.branches:
            if branch.label != HOURS[branch.hour_index] + "时":
                raise ValueError("Golden branch label does not match the engine hour index")
        return self


def load_golden() -> ChartGolden:
    return ChartGolden.model_validate(yaml.safe_load(FIXTURE.read_text(encoding="utf-8")))


def structure_checks(text: str) -> dict[str, bool]:
    # A named convention and an actual chart reference matter; no element is a fixed answer.
    absolute = re.sub(r"(?:不代表|不意味着|并非|不是|不会|不能|不)(?:一定|注定|必然)", "", text)
    double_negative = bool(re.search(r"(?:不是|并非|并不|不代表|不意味着)不(?:一定|注定|必然)", text))
    return {
        "citation": bool(re.search(r"〔c[1-9]\d*〕", text)),
        "school": bool(re.search(r"子平|调候|格局|旺衰|盲派|三合|钦天|飞星|[\u4e00-\u9fff]{2,8}流派", text)),
        "basis": bool(re.search(r"盘面|命盘|月令|日主|日干|四柱|五行|寒暖|干支", text)),
        "no_absolutes": not double_negative and not bool(re.search(r"一定|注定|必然|唯一正确|必定大富", absolute)),
        "no_rule_gap": not bool(re.search(r"RULE_GAP|规则缺口|尚未实现|尚无覆盖|缺少已实现规则", text)),
    }


def stability_checks(text: str, golden: ChartGolden) -> dict[str, bool]:
    negative = r"不稳定|不一致|不相同|存在变化|(?:不能|无法)(?:确定|保证)?.{0,6}稳定"
    stripped = re.sub(negative, "", text)
    positive = bool(re.search(r"(?:区间|全部|所有|采样|样本).{0,12}(?:稳定|一致|相同|一样)", stripped))
    negative_found = bool(re.search(negative, text))
    correct = positive and not negative_found if golden.sampled_stable else negative_found and not positive
    checks = {"stability": correct}
    labels = "|".join(re.escape(branch.label) for branch in golden.branches)
    for branch in golden.branches:
        spans = re.findall(re.escape(branch.label) + r"(?:(?!(?:" + labels + r"))[\s\S]){0,100}", text)
        checks["branch_" + str(branch.hour_index)] = any(
            all(star in span for star in branch.major_stars) for span in spans
        )
    return checks
