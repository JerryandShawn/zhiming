# MOD：旧消息变更集桥接的 15 项独立边界验证

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。四个活段落必须随 root 后续授权和真实结果更新。
创建时间：`2026-10-21T10:41:20.490208+08:00`，一律北京时间；主机 Tokyo 时区不是记录依据。

## Purpose / Big Picture

验证“已审阅的新实体标签计划”转换到另一个当前旧消息文档时，不能覆盖不同 owner、主体、原话或修订。
旧桥只是生成可预览的 `ChangeSet`（记录字段变动及逆操作的变更集），不连接数据库，也不实际应用。
最初只冻结 15 项独立期望及摘要。root 在 10:45 全量结束后明确放行独立 Python 实施及一次目标首测。
首测 1 项失败、14 项通过的原始历史保留。root 随后只在旧桥增加 strict raw scalar 门禁，
并明确放行原 15 项复测及两套整理兼容/一次限定覆盖；现已分别通过 15 项与 529 项。
本验证者没有修改任何产品、既有断言或冻结真值；后续扩展仍须 root 决定。

## Context and Orientation

唯一工作目录是 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
公开入口是 `mingjing_core/organize/supplement_v2/legacy_bridge.py` 的
`to_legacy_changeset(snapshot, plan, document, *, scope, approval)`。
复用 `review.py:24` 的 `build_review_proposal`、`:128` 的 `plan_review_labels`、
`projection.py:125` 的 `project_plan`、`lifecycle.py:34` 的 `plan_topic_archive`、
`:63` 的 `plan_archive_review`；不自行伪造获批计划或调用私有验证函数。
`organize/contracts.py:8` 的 `Message` 是旧消息公开契约，revision 的默认值是整数 1，布尔值不合法。
`organize/changes.py:104` 的 `ChangeSet.from_documents` 仍负责旧标签变更的验证；本轮不改它。

获批计划是宿主校验用户身份后提供的可信审阅收据，不是模型或客户端自称的授权。
原话锚点是指向当前来源确切字串与版本的引用，不能因文本相同就换成另一条消息。
字段“缺失”与显式 `null` 不同，变更和逆操作必须保留这种差别。
完整消息桥是有意缩小的适配入口：部分、多源等合法通用实体映射需要其他适配器，不能据此宣布它们非法。

设计依据为脑交付 `33_全量开发队列_本周.md` 第四节 6/8 与无尽储备的公开异常边界；
`docs/v4/prompts/supplements/P5b_功能区与旧对话整理.md` A.5/A.7/E；
`docs/v4/integration/mod/DAY_supplement_20261021.md` 的审阅边界及第 54 行完整消息限制。
冻结前桥接直接测试只有 `tests/v4/organize_supplement/test_supplement_mod.py:315` 的成功转换、
应用撤销及非 message 拒绝；另一个独立测试文件已有通用来源/审阅/逆操作保护，不重复其真值。
旧 191 产品覆盖盘点只帮助定位入口，不以覆盖数字决定测试意义，也不把本轮未运行案例归入旧证据。

## Progress

- [x] (2026-10-21T10:41:20.490208+08:00) 冻结两文档、15 例和 15 源/2 既有测试摘要，未运行探针。
- [x] (2026-10-21T11:04:24.746286+08:00) 一次首测：1 failed / 14 passed in 0.23s；LB08 原始返回与历史源摘要保留。
- [x] root 只在 legacy_bridge 增加严格原始 revision/at_ms 类型门禁；测试和两组冻结真值不动。
- [x] (2026-10-21T11:11:22.696365+08:00) 原 15 项修后复测：15 passed in 0.14s；32 执行快照无漂移。
- [x] (2026-10-21T11:12:17.369754+08:00) 两套整理兼容及单次限定 coverage：529 passed in 2.11s，33 快照无漂移。
- [x] (2026-10-21T11:14:40.145984+08:00) 更新四活段落，新增接线补充及 §11 回执；无后续 Python 编辑、额外测试或 Git。

## Surprises & Discoveries

首测确认 LB08 的布尔 True 冒充 revision=1，公开 Message 拒绝同输入，但旧桥曾返回 4 个标签操作。
root 另一独立 5 项首测同时观察到等值 float revision、float at_ms、bool at_ms 的同类接受面扩大；原历史各自保留。
root 的最小通用修复只要求原始 revision（缺省 1）为真正正整数，原始 at_ms 为真正整数；不做 int 转换或补字段。
修后原 15 项全部通过；两套兼容实际包含 IB01-IB05，529 项通过。
LB15 缺失 revision 保持缺失，独立 IB02 匹配 revision=2、IB05 整数 epoch 0 仍合法。
未另增负整数时间测试，不能把代码未限制正负外推成该分支已实测全部负值。
覆盖只计 supplement_v2 九产品：bridge 行 46/46、分支 26/26；全九文件综合 705/803=87.7958%，尚未达 90%。
该范围残余路径主要在 contracts/lifecycle/projection，报告逐项列明；本轮不为追数字擅自补例。

## Decision Log

两组原断言和矩阵均未改；本验证者没有改产品。LB08 不预设新错误码，修复复用 legacy_message_evidence_changed。
原首测完整输出、失败 trace 和旧源码 SHA 仍为历史证据，不覆盖为通过结果。
原 15 项修后另存 postfix；兼容与覆盖另存第三份报告，避免把插桩时间作为性能或把 529 冒充全项目回归。
使用 runner.environment 移除 12 类凭证并关 tracing；只绑定实际产品、两套全部 Python、合成/冻结输入及历史证据。
按 root 提醒，runner 的无关追加与活 ExecPlan 不纳入域快照，不因它们后续维护宣称产品漂移。
保持 owner/subject、来源角色/版本/撤回/无痕、审阅指纹和敏感授权；不新增连续版本/完整历史 prefix 要求。
没有模型、网络、PG、真实 apply/undo、Git 操作，也不读取盲评 B 或私人校准正文。

## Outcomes & Retrospective

本轮获授权的独立原 15 项与必要两套兼容均已完成并通过，首失败历史和原矩阵保留不变。
原 15 项修后 15 passed in 0.14s；两套目录合计 529 passed in 2.11s，明确包含独立 IB01-IB05。
postfix 开始 `2026-10-21T11:11:21.535788+08:00`，结束 `2026-10-21T11:11:22.696365+08:00`；32 快照无漂移。
兼容/覆盖开始 `2026-10-21T11:12:13.811453+08:00`，结束 `2026-10-21T11:12:17.369754+08:00`；33 快照无漂移。
9 产品行 554/603=91.8740%、分支 151/200=75.5000%、综合 705/803=87.7958%；旧桥自身行/分支均 100%。
不是整 PR/项目覆盖，不是性能测量，剩余覆盖未达 90% 的事实如实保留。
新指南 `docs/v4/integration/mod/LEGACY_BRIDGE_boundary_20261021.md` 和 §11 回执已新增；旧指南不改。
真实用户审阅、PG 事务、实际应用/撤销、CI 和部署状态未由本任务验证。后续无新增工作授权，当前冻结交 root。

## Plan of Work

里程碑一是本次文档冻结：JSON 记录精确输入变化、预期、独立依据、当前源与已有测试原始字节摘要。
里程碑二已在 root 明确放行后实施：新增
`tests/v4/organize_supplement_v2/test_legacy_bridge_calendar_mod.py` 与必要独有 helper，
使用公开构造器和审阅 API，不导入产品私有 helper、不重 seal 伪造状态、不调用冻结分类器。
唯一新增合成正文位于 `tools/eval/fixtures/mod_20261021/legacy_bridge_calendar_synthetic.json`，显式 synthetic=true。
里程碑三的一次单目标首测已完成：保存 stdout、返回/领域异常、时间和前后摘要，LB08 实缺已报 root，不先修产品。
首测之后 root 单独授权两套整理兼容及一次仅 supplement_v2 的覆盖，已完成；性能和跨项目全量没有授权或执行。

## Concrete Steps

root 先后明确放行一次首测、一次修后原目标与一次两套兼容/限定覆盖，均已用 Core Python 3.11 完成；禁止自行再次执行。
通过 runner.environment 移除 12 类凭证、关闭 tracing，临时目录位于
`private/mod-week/tmp`，仅单个测试进程；输入采用固定合成来源时刻和 `Asia/Shanghai`。
首次实际命令另含 `-s --tb=short` 与唯一工作区 basetemp；完整 argv 在首测 JSON，下述为其核心：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -B -m pytest tests/v4/organize_supplement_v2/test_legacy_bridge_calendar_mod.py -q

不得对既有目录运行格式化或自动修复。新增 Python 仍须单文件 ≤400、函数 ≤60、行 ≤120 和完整类型标注。

## Validation and Acceptance

`docs/v4/07_评测场景集.md` F03 的来源删除传播是不得绕过的背景契约；本轮不声称执行 F03 的完整系统验收。
P5b SP06 的应用/撤销逐字段还原是标签变更背景，现有桥接正常链已覆盖；本轮增加以下精确公开边界。
各例先满足当前 scope、来源、锚点、版本及审阅条件；除表列内容外不改变获批输入，避免无关失败掩盖目标门禁。

| ID | 唯一变化或公开输入 | 独立预期 |
| --- | --- | --- |
| LB01 | 仅 document.owner_id 与获批 scope 不同 | legacy_document_scope_mismatch |
| LB02 | 仅 document.subject_id 与获批 scope 不同 | legacy_document_scope_mismatch |
| LB03 | document.messages 为合法空字典，其他目录合法 | legacy_message_missing |
| LB04 | 仅目标旧消息 content 与当前原始来源不同 | legacy_message_evidence_changed |
| LB05 | 当前来源仍为 user，仅旧消息 role 改为 assistant | legacy_message_evidence_changed |
| LB06 | 仅目标旧消息 at_ms 增加 1 毫秒 | legacy_message_evidence_changed |
| LB07 | 实体和来源均为 revision 1，仅旧消息 revision 改为整数 2 | legacy_message_evidence_changed |
| LB08 | 实体和来源均为 revision 1，仅旧消息 revision 改为布尔 True | 受控拒绝，不生成 ChangeSet；固定安全原因，不预设错误码 |
| LB09 | 获批实体 labels 无 topic_id；仅旧消息增加 topic_id: null | legacy_message_labels_changed |
| LB10 | 通过公开 API 建立合法实体与当前来源；来源 ID 与实体消息 ID 不同，正文完全一致 | message_source_identity_mismatch |
| LB11 | 当前消息实体仅绑定同源有效子串，非完整原话；先通过公开审阅 API 建立合法计划 | complete_message_source_required |
| LB12 | 当前实体绑定两个有效锚点并取得合法审阅计划，不伪造内部状态 | mainline_entity_adapter_required |
| LB13 | source 与有效 anchor 均为 revision 2；实体及旧消息为 revision 1；公开审阅计划先合法成立 | legacy_message_revision_changed |
| LB14 | 通过公开话题归档和审阅 API 取得合法 topic-only 计划；旧文档结构合法 | mainline_topic_adapter_required |
| LB15 | 仅省略目标旧消息 revision；实体与来源为 revision 1，其他证据及标签全部一致 | 允许仅标签 ChangeSet，revision 缺失保持缺失 |

拒绝例不返回变更集；领域错误不能含合成正文。所有 15 例输入快照、原文档和获批内容均不被修改。
LB15 返回操作只允许 messages 标签白名单，正文、角色、时刻、来源和 revision 键缺失状态保持原样。
具体冻结真值以 JSON 的 `cases` 为准，其 canonical SHA256 为 `d2a66eac57234f68afc8c602394a8b359628addb8f4d7a938271840acdefa711`。

## Idempotence and Recovery

文档生成只新增文件，若路径已存在则拒绝覆盖；无数据库迁移、删除、回填或运行状态变动。
未来测试使用独立内存输入，重跑不影响真实数据。发现反例先保存首轮，再等待 root 选择必要产品修复。
恢复不意味着撤销来源：现有来源撤回和逆操作门禁继续生效，不以成功生成变更集证明实际 apply 获批。

## Artifacts and Notes

冻结矩阵为 [LEGACY_BRIDGE_frozen_matrix_20261021.json](../evidence/MOD_2026-10-21/LEGACY_BRIDGE_frozen_matrix_20261021.json)。
冻结矩阵原始 UTF-8 LF SHA256：`883b171aa7589aa1ee807d439c1779714ee91f588c9a2b0755b269b07b3491b2`；这是文件摘要，不是 Git commit。
JSON 内冻结 15 份相关产品源码和 2 份既有测试哈希，不修改它们。
首测报告现已保存为 `docs/v4/evidence/MOD_2026-10-21/LEGACY_BRIDGE_independent_first_20261021.json`，
SHA256 `6bb2395267b4462f8657fae8a49f0d59490ca18cf0baa6a09af75674f3661adc`。root 独占 Git，本轮不查询或声称当前提交、CI、部署状态。
修后和兼容覆盖证据分别见同目录的 LEGACY_BRIDGE_independent_postfix_20261021.json 与
LEGACY_BRIDGE_compatibility_coverage_20261021.json；两者 SHA 及范围见新增指南。

## Interfaces and Dependencies

不新增公共产品接口、API、数据表、迁移或依赖。公开入口签名保持：

    to_legacy_changeset(snapshot: SupplementSnapshot, plan: SupplementPlan, document: dict, *, scope: MemoryScope, approval: ReviewApproval) -> ChangeSet

未来 setup 只复用 `SupplementSnapshot/EntityRecord/MemorySource/SourceAnchor/Prediction/ReviewApproval`、
`build_review_proposal/plan_review_labels/plan_topic_archive/plan_archive_review`。
Prediction 是显式合成输入，不调用分类器或读取其评测标签；预期来自设计/公开契约，不用产品输出造黄金。

## 修订记录

- 2026-10-21T10:41:20.490208+08:00：root 授权仅新增计划及矩阵，冻结 15 例和当前摘要，尚未实施或运行；保持 10:45 全量代码冻结。

- 2026-10-21T11:05:48.708911+08:00：按 root 后续授权新增独立测试并首测，保存 1 失败/14 通过真实证据；更新四活段落，原矩阵与产品不动。

- 2026-10-21T11:14:40.145984+08:00：root 最小 strict guard 后，原 15 与两套 529 兼容通过；新增限定覆盖、接线补充及 §11 回执，旧首失败保留。
