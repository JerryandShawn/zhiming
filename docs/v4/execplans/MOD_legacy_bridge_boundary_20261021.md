# MOD：旧消息变更集桥接的 15 项独立边界验证

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。四个活段落必须随 root 后续授权和真实结果更新。
创建时间：`2026-10-21T10:41:20.490208+08:00`，一律北京时间；主机 Tokyo 时区不是记录依据。

## Purpose / Big Picture

验证“已审阅的新实体标签计划”转换到另一个当前旧消息文档时，不能覆盖不同 owner、主体、原话或修订。
旧桥只是生成可预览的 `ChangeSet`（记录字段变动及逆操作的变更集），不连接数据库，也不实际应用。
本轮只冻结 15 项独立期望及现有源码/测试摘要，不新增 Python，不测试，不把静态风险称为产品缺陷。
root 的 10:45 全量冻结继续有效；本计划不构成未来运行或修产品的授权。

## Context and Orientation

唯一工作目录是 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
公开入口是 `mingjing_core/organize/supplement_v2/legacy_bridge.py:39` 的
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
现有桥接直接测试只有 `tests/v4/organize_supplement/test_supplement_mod.py:315` 的成功转换、
应用撤销及非 message 拒绝；另一个独立测试文件已有通用来源/审阅/逆操作保护，不重复其真值。
旧 191 产品覆盖盘点只帮助定位入口，不以覆盖数字决定测试意义，也不把本轮未运行案例归入旧证据。

## Progress

- [x] (2026-10-21T10:41:20.490208+08:00) root 接受只读 15 例计划，完整读取入口、公开契约、调用方和已有直接测试。
- [x] (2026-10-21T10:41:20.490208+08:00) 新增本 ExecPlan 和冻结 JSON；记录 15 源、2 既有测试、设计文档的原始 SHA256。
- [ ] root 在 10:45 全量结束后明确放行 Python 实施；当前没有放行，不创建测试/helper/正文 fixture。
- [ ] 按冻结矩阵新增独立公开测试，先保存首轮真实结果与源码/测试哈希，再报告 root。
- [ ] 只有必要修复获 root 授权后才复测；本计划本身不授权修改产品或既有真值。
- [ ] 保存最终 LF 证据、Ruff/AST 与 §11 回执，四活段落如实更新后冻结交回 root。

## Surprises & Discoveries

只读时发现旧桥用原始字典字段相等比较，公开 `Message` 则明确要求 revision 为真正整数。
LB08 可能成为可复现反例，也可能在其他公开门禁被受控拒绝；目前未导入产品、未运行探针，不能据此报缺陷。
缺失 revision 的合法默认 1 兼容必须保留，不能为了 LB08 一并拒绝 LB15。

## Decision Log

本轮限定 15 例，不增加字典形状、分类质量或完整历史等新契约。root 已审核接线指南并明确允许先冻文档。
LB08 只断言严格整数边界下受控拒绝：允许公开 ValueError 家族的固定安全错误，不预先发明新错误码；
不能把 AttributeError、TypeError 或 KeyError 等原始结构异常算成通过。
LB10-LB13 先通过公开 API 建立合法通用映射，再验证完整消息专用桥的限制，不凭感觉拒绝不完整来源。
保持原 owner/subject、源角色/版本/撤回/无痕、审阅指纹、敏感授权及未知状态不重发等现有门禁。
不重复 memory24、calendar28、brief30+8、CLI8；不读 Q5 盲评 B、真实历史或私人校准正文。

## Outcomes & Retrospective

当前完成的是可复核的文档冻结，不是 15 项测试通过。新增文件恰为两份，不新增或修改 Python。
测试、覆盖、性能、数据库、真实用户审阅及外部投递均未运行/未验证；没有产品修改或实缺结论。
下阶段实施和运行须 root 另行授权，首轮原始观察必须保留，不能根据当前输出放松矩阵。

## Plan of Work

里程碑一是本次文档冻结：JSON 记录精确输入变化、预期、独立依据、当前源与已有测试原始字节摘要。
里程碑二仅在 root 放行后开始：拟新增
`tests/v4/organize_supplement_v2/test_legacy_bridge_calendar_mod.py` 与必要独有 helper，
使用公开构造器和审阅 API，不导入产品私有 helper、不重 seal 伪造状态、不调用冻结分类器。
未来合成正文只放 `private/` 或 `tools/eval/fixtures/` 下明确 synthetic 文件；本轮不创建正文。
里程碑三是一次单目标首测：保存 stdout、返回/领域异常、时间和前后摘要，实缺立即报 root，不先修产品。
兼容、覆盖、性能和全量不随目标首测自动获得授权。

## Concrete Steps

当前只允许检查两份新文档及冻结摘要，不能运行以下未来命令。
未来获 root 明确放行后，在上述工作目录中用 Core Python 3.11，显式空密钥、禁 tracing、临时目录位于
`private/mod-week/tmp`，仅单个测试进程；输入采用固定合成来源时刻和 `Asia/Shanghai`。
拟单目标命令如下，当前未执行：

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
当前矩阵原始 UTF-8 LF SHA256：`883b171aa7589aa1ee807d439c1779714ee91f588c9a2b0755b269b07b3491b2`；这是文件摘要，不是 Git commit。
JSON 内冻结 15 份相关产品源码和 2 份既有测试哈希，不修改它们。
未来首测报告拟为 `docs/v4/evidence/MOD_2026-10-21/LEGACY_BRIDGE_independent_first_20261021.json`，
目前不存在本阶段运行结果。root 独占 Git；本轮不查询或声称当前提交、CI、部署状态。

## Interfaces and Dependencies

不新增公共产品接口、API、数据表、迁移或依赖。公开入口签名保持：

    to_legacy_changeset(snapshot: SupplementSnapshot, plan: SupplementPlan, document: dict, *, scope: MemoryScope, approval: ReviewApproval) -> ChangeSet

未来 setup 只复用 `SupplementSnapshot/EntityRecord/MemorySource/SourceAnchor/Prediction/ReviewApproval`、
`build_review_proposal/plan_review_labels/plan_topic_archive/plan_archive_review`。
Prediction 是显式合成输入，不调用分类器或读取其评测标签；预期来自设计/公开契约，不用产品输出造黄金。

## 修订记录

- 2026-10-21T10:41:20.490208+08:00：root 授权仅新增计划及矩阵，冻结 15 例和当前摘要，尚未实施或运行；保持 10:45 全量代码冻结。
