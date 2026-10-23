# Q2：把结构检查、旧 lint 与独立评审接进 v4

本说明补齐主线 finalize 的顺序和适配边界。[既有 P6 评审/校准指南](../P6_critic_calibration_mod.md)保留详细 15 项 rubric、统计定义与校准来源门槛，这里不重复长表。设计依据：[P6 原提示](../../prompts/P6_校验2.0与安全.md)、[P6 增补 A–D](../../prompts/supplements/P6_增补_评审校准.md)。

本分支只实现纯函数/受控投影。没有发评审请求、写运行账本、执行 Agent 修订或改 v3 校验入口；单元测试不能证明真实评审质量，也没有生成真实人标报告或开启生产修订项。

## 真实入口与类型

| 入口 | 作用与主线依赖 |
| --- | --- |
| [StructuralContext / Result / Finding](../../../../mingjing_core/validation/structural_contracts.py) | 提供同一次 Clock 快照、owner 时区、当前有效别名、真实回执、ask_user 次数、最后模型文本及 farewell 状态 |
| [structural_check(text, context)](../../../../mingjing_core/validation/structural.py) | 返回交付文本、全部 finding 与 ask_user_allowed；确定性修正/附注/空文兜底，内部失败仍保留回答 |
| [LintContext / lint(text, context)](../../../../mingjing_core/validation/legacy_lint.py) | 旧 13 类规则只返回 Finding；显式 snapshot/calculation/plan/run_request/final_answer，可注入纯 revalidator |
| [CriticMaterials / build_critic_request](../../../../mingjing_core/validation/critic_request.py) | 单轮白名单投影；新会话请求描述，固定 critic/k3-256k/high；本函数不发请求 |
| [parse_attempts / compute_review](../../../../mingjing_core/validation/critic.py) | 只解析最多两份已经取得的输出；程序计算 verdict、sample_queue、一次修订/危机例外 |
| [ProgramIssue / ReviewResult](../../../../mingjing_core/validation/critic_contracts.py) | 可信程序问题与模型问题分开，severity 归程序；结果含私人引句，不能写公共日志 |
| [calculate_calibration](../../../../mingjing_core/validation/calibration.py) | 人标与评审二值标签、身份/来源声明 → 分项 κ、敏感度/特异度、Wilson 与状态；没有人标则 record_only |

## finalize 的事务和事件顺序

1. 主线先验证 run/owner/subject/thread、来源撤销 epoch、当前 lease 和运行状态，捕获本轮确定的 UTC `program_at`。把它包装为一次固定 Clock，结构检查与给评审的 `<此刻>` 使用同一时刻和 owner 时区，避免跨午夜各算一次“今天”。
2. 保留已经流给用户的初稿与 `last_model_text`，执行 structural_check。未知别名被移除，星期可确定时直接改正；相对日期错且评审不可用时追加设计中的固定日期附注；空答案兜底。保存所有 finding 的 code 和修改记录。
3. 对结构处理后的全文执行 legacy lint，写 `review.lint[]` 和计数。lint 不阻断、不修订；不能把其 advisory severity 当成已校准 critic 或可信程序证据。
4. 从仍未解决的确定性问题生成当前草稿绑定的 ProgramIssue。额度守卫允许 critic 时，构造独立材料与完整 v2.0.0 提示词，通过主线唯一模型端口发请求；超时、额度不足或不可用时用 evidence_only，照常保留交付文本。
5. 使用同一份草稿与 evidence_ids 解析已经取得的输出。最多一次解析重试所需的物理请求仍由主线守卫计数；parse_attempts 自己不发请求。程序计算 review，普通修订最多一次；未校准模型项、低置信或低严重度只记录。
6. 若需要且允许修订，主线在同一运行内提交受控修订；追加 `text_reset(reason="revised")`，修订稿再跑结构检查，之后不再调用普通评审。E6 危机漏判是次数例外，仍保留其置信/来源门槛；真正危机生成与热线模板由主线接入。
7. 最终提交前重新检查 lease、source epoch 与撤销状态，原子保存最终文本/版本、revision 次数和 review 元数据，再发布最终事件。校验失败开放不等于可以绕过鉴权、撤销或把旧运行的私人内容重新投递。

网络模型调用不能放进长 PG 锁事务。调用前后分别检查受控快照与运行身份，使用主线 journal/lease 防止中断后重复修订。普通校验或模型不可用时交付已存在的初稿/结构处理文本，不再把用户回答替换为旧的“本轮阶段未完成”。

## StructuralFinding → ProgramIssue 必须显式适配

两种类型不是同一个契约，不能直接解包，也不能把模型 JSON 转成 ProgramIssue。

| 结构发现 | 主线应做的映射 |
| --- | --- |
| weekday_fixed | 已确定性改正；保留原 finding/run meta，视为 resolved，不要求普通修订 |
| time_error / E1，evidence 为 clock:日期 | 对照本轮 now_block 后注册/映射为 `now` 或真实 `now:N`，quote 必须仍是当前草稿的连续子串 |
| false_receipt / E2，evidence 为 receipts:missing_corresponding_success | 对照本轮真实回执清单，映射为 `receipts`；空清单也是真实“无对应成功”证据 |
| unknown_alias、empty_answer、ask_user_limit、farewell_question_removed 等 item=None | 保存程序 finding；不强行伪造 E/J 项，不直接作为 critic 模型修订授权 |

已经被删掉/改掉的原句不能塞进修正后 CriticMaterials。`ProgramIssue(resolved=True)` 可用于主线可信的裁决记录，但如果其 quote 不在当前草稿，不能放进当前评审请求；将这类记录单独留在 run meta。`CriticMaterials` 对 program quote 与本次 evidence_ids 有实际存在性检查。

同一 item 可能有多条程序发现，compute_review 按二值 rubric 要求每项唯一。适配器需要确定性归并到每项至多一个 ProgramIssue，同时完整保存原 findings；不能丢失其他日期/回执问题。可为同类问题建立实际聚合证据摘要 ID，quote 取当前稿中的真实连续原句，fix_hint 描述该类待修内容。只在确有对应材料时注册证据 ID，不能单纯把任意字符串塞进白名单。

别名传裸名如 `c3/f1`，不是带 `〔〕` 的显示文本。回执只取同 owner、当前 run/epoch、目标对应且仍有效的程序结果；`saved/updated` 才授权保存断言，pending/stopped 等不算。不能用一条无关 saved 回执授权整段“已保存”。

`ask_user_allowed` 只是纯规则结果。每轮第二次 ask_user 必须在工具执行入口、数据库写入和 ends_turn 之前被主线拒绝，不能等最终文本出来后才告警。

## 可运行的 evidence_only 适配例子

以下只用合成材料演示当前草稿/证据映射和程序裁决。它不发模型请求，也不执行修订或存储；实际应用仍须遵循上面的身份/事务边界。样例每项只有一个程序问题，真实适配器还需实现上一节的同项归并。

```python
from datetime import UTC, datetime

from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.critic import compute_review, parse_attempts
from mingjing_core.validation.critic_contracts import ProgramIssue
from mingjing_core.validation.critic_request import CriticMaterials
from mingjing_core.validation.legacy_lint import LintContext, lint
from mingjing_core.validation.structural import structural_check
from mingjing_core.validation.structural_contracts import StructuralContext

clock = FrozenClock(datetime(2026, 10, 18, 4, tzinfo=UTC))
checked = structural_check(
    "明天是10月22日。我已经保存了喜欢徒步。",
    StructuralContext(clock=clock, receipts=(), critic_available=False),
)
lint_findings = lint(
    checked.text,
    LintContext(
        snapshot={"facts": []},
        calculation={"claims": [], "calculation": {}},
        plan={"decision": False, "mode": "conversation", "systems": []},
        run_request={"message": "合成消息"},
    ),
)
program = tuple(
    ProgramIssue(
        finding.item, finding.quote, finding.rule,
        "now" if finding.item == "E1" else "receipts", finding.fix_hint,
    )
    for finding in checked.findings
    if finding.item in {"E1", "E2"} and finding.code != "weekday_fixed"
)
materials = CriticMaterials(
    user_message="合成消息", now_block="2026-10-18 周日", draft=checked.text,
    program_issues=program,
)
parsed = parse_attempts([], draft=materials.draft, evidence_ids=materials.evidence_ids)
review = compute_review(parsed, program_issues=materials.program_issues, critic_allowed=False)
assert review.mode == "evidence_only" and review.verdict == "revise"
assert checked.text and lint_findings  # 回答仍存在；lint 没有吞掉它。
```

若守卫允许 full，主线读取大脑的完整 critic v2.0.0 运行时提示词，再调用 build_critic_request；不能用只有版本注释的假提示词。请求只含本轮消息、此刻、授权事实/声明/命理档案摘要、回执、当前稿及程序问题；禁止传主 messages/system/reasoning/tool traces/history。版本头校验不等于提示词全文已正确同步。

## 旧 lint 与自由文本兼容

旧 `_validate` 在 [consultation.py](../../../../mingjing_core/application/consultation.py) 的源码 SHA256 为 `1a041a66ff95bc50fd5e1bf9642c95e34bfc0386ac4e03baf2c9709cbb365fdb`；13 类规则完整迁到新文件，没有运行时委托。v3 仍调用原校验并保持旧行为，到 P11 前不要替换它的 `_phase_validation` 或 [runtime/graph.py](../../../../mingjing_core/runtime/graph.py) 来假装已接上 v4。

`lint(text, context)` 的 text 应覆盖实际交付全文和专业附录。兼容 v3 结构时传 `render_answer(final) + "\n" + final["professional_appendix"]`；v4 自由文本可不传 final_answer，或从当前真实工具结果/引用追踪生成兼容结构投影。不要重新要求模型生成旧 FinalAnswer 才能交付。

旧兼容 schema 的 plain_summary 上限 6000 字。长自由文本若直接用默认投影，会得到 lint_schema_error；这不应截断交付答案。主线若要继续运行完整文本 lint，应只给兼容结构中的摘要字段提供有界投影，完整 text 仍原样传入；actions/decision_options/cited IDs 从真实本轮结构记录补齐，不得编造。span=None 表示旧聚合规则没有精确定位，severity 是新 advisory 元数据，不是原 v3 的评分事实。

有声明时应注入既有纯 `revalidate_claims(calculation, claims, tarot_provenance)` 依赖。缺依赖会产生 legacy_revalidation_unavailable，不能称为已重验；schema 或内部异常只返回固定告警，不把异常中的私人正文放进消息。

## 主线要改的已有边界与尚未实现项

| 已有位置 | 主线需要做的接线 |
| --- | --- |
| [adapters/web.py](../../../../mingjing_core/adapters/web.py) | v4 runtime 路由、当前草稿和修订事件输出；私有 review 数据的访问与展示投影 |
| [adapters/channels/hermes.py](../../../../mingjing_core/adapters/channels/hermes.py) | 与 P4 协议一起扩展信封的 review/text_reset 兼容投影，不能把内部引句全部送公共诊断 |
| [config/models.yaml](../../../../config/models.yaml) | critic 身份/effort 与 P1b 配置保持一致；实际切换及等价性验证归主线授权流程 |
| [tools/eval/runner.py](../../../../tools/eval/runner.py)、[report.py](../../../../tools/eval/report.py) | 主线接种子缺陷、宽松度与配对统计，冻结 v2.1 不因本模块改写；新场景按约定版本隔离 |
| [旧行为覆盖表](../../../../docs/CORE_V3_BEHAVIOR_COVERAGE.json) | 主线 P6 为旧行为标注新的覆盖位置，保留原条目 |

完整 P3 的 Agent finalize/工具 dispatcher/journal 在本分支基底尚未落地，不能把它们写成已经改过的文件。主线在自己的 P3/P6 分支接入新循环、review 配置、提示词、校准导入、危机支持与持久化修订次数。本模块没有新增或占用数据库迁移号。

校准来源声明必须由主线核实；合成测试的 perfect labels 不是真实人工复核。实际 60+ 全 15 标签、用户复核/分歧裁定、种子缺陷与宽松度、真实模型质量、危机/零吞答案全链路、schema 错误后的实际 UI 行为和真实 PG 撤销并发均未在这里完成。ReviewResult.as_dict 含引句与证据，应按私人运行数据存取；公共日志只记受控 code/item/计数/耗时。

## 本地验证

在仓库根目录激活 Core Python 3.11，以下不连数据库或模型：

```powershell
python -m pytest tests/v4/validation -q
python tools/mod_overnight/verify_legacy_parity.py
python -m ruff check mingjing_core/validation tests/v4/validation --select E,F,I,B,UP,SIM --line-length 120
python -m ruff format --check mingjing_core/validation tests/v4/validation --line-length 120
```

[Q2 证据](../../evidence/MOD_2026-10-19/Q2_validation_metrics.json)为 880 项纯测试；旧 lint 有 96 条答案来自 26 份显式合成转录的 oracle 差分，补充 literal 审计为原 99 次/81 个唯一正则、丢失 0。该证据只证明迁移和纯裁决行为；主线完成接线后仍须运行真实隔离 PG、受控模型替身的 finalize/一次修订/超时/撤回集成测试，真实评审调用另按 D1 和当前用户授权执行。
