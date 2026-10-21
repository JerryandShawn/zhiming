# MOD P5b E：把合成v3导出转为可审阅的离线变更候选

本ExecPlan遵循`.agent/PLANS.md`，是活文档。时间一律为北京时间。

## Purpose / Big Picture

新增一个不连接存储的转换器：输入显式合成的v3导出和可信host当前快照，输出归区、话题、冲突与撤销候选。
dry-run是“只计算会改什么”，不是批准或执行修改。原话、回答、时间、来源版本都保持不变。
用户未来可在整理页审阅预览；本模块没有应用、删除、发消息、起标题模型或数据库入口。
真实v3导出映射、stage试跑、用户批准和正式应用仍归主线，逐次授权。

## Context and Orientation

工作根目录为`C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
设计依据：大脑交付目录33号第四节第6项；18/P5b E与A.5；22号§5、§7。
33/P5b/22全文与AGENTS、PLANS已于本次开工完整阅读。

复用但禁止修改的现有接口：

- `mingjing_core/organize/v2/classifier.py:67`：冻结Q5 `LocalClassifier.classify`，不调参、不读盲评B。
- `mingjing_core/organize/v2/topics.py:40`：`cluster_messages`只给user消息聚类；assistant关联不变成用户事实。
- `mingjing_core/organize/changes.py:96`：只用`ChangeSet.from_documents`生成标签/新话题候选，不用MemoryChangeStore。
- `mingjing_core/organize/_change_values.py:40`、`:60`、`:81`：FieldValue/FieldChange/SourceGuard，保留字段缺失与null的差别。
- `mingjing_core/organize/_change_values.py:133`：验证完整消息/话题目录，拒绝越界改原话。
- `mingjing_core/organize/supplement_v2/contracts.py:20`：标签allowlist；`:guards.py:16`固定JSON摘要算法。
- `mingjing_core/memory2/sensitivity.py:110`：敏感、secret与出生资料分类；分类不是保存授权。
- `mingjing_core/memory2/contracts.py`：MemoryScope/MemorySource/SourceAnchor与明确UTC。

冻结P9、Q1至Q6、supplement_v2、Q5语料/分类器/评测器均不改。合成正文只放显式synthetic fixtures或private。

## Progress

- [x] (2026-10-21 07:42) 阅读33/P5b/22与代码接口，定义纯dry-run边界。
- [x] (2026-10-21 07:58) M1：新增独立契约、synthetic导入codec与来源/owner/revision/epoch门禁。
- [x] (2026-10-21 07:58) M2：冻结Q5用户分类/话题候选、assistant仅继承、标签变更集与冲突。
- [x] (2026-10-21 07:58) M3：审阅预览、幂等ledger与撤销候选；61项目标自测、100组属性组合通过；独立验收进行中。
- [x] (2026-10-21 08:00) M4：最终67自测+89独立=156项通过；Ruff/AST、接线、final性能与本地阶段回执完成，交root提交。

## Surprises & Discoveries

现仓库没有可核实的v3导出文件规范。本次明确建立`zhiming.v3.synthetic_export.v1`中间格式，不冒称已兼容真人导出工具。
主线必须先写真实v3到该中间格式的受保护映射，之后才可谈stage或正式迁移。

supplement的实体授权复用MemoryFact门禁，适合事实与标签审阅，但不能把assistant原回答伪装成user来源。
本模块只复用其标签校验与敏感策略；对完整transcript使用独立的当前来源/角色/原话核对。
所有输出都只是标签意图；没有任何MemoryFact创建或记忆保存。

首轮25个失败来自同一个seal编码错误：TopicCandidate.message_ids tuple被传给旧strict JSON摘要器。
产品改为显式JSON list后原36断言通过，没有改旧摘要函数或降低真值。
独立验收唯一夹具适配是并发move同步当前消息及话题的区，避免把非法目录误当合法并发；未放松目录校验。

## Decision Log

2026-10-21 07:42，模块线：输入只接受host标记synthetic的显式中间格式；未授权真实导入保持不可执行。
这是离线范围限制，不是对未来主线真实迁移格式的产品决定。

2026-10-21 07:42，模块线：仅user文本进入冻结Q5。assistant在同线程、此前user的6小时窗口内继承其候选；
孤立回答进入待整理，保留自己的source anchor，不作事实或用户断言。

2026-10-21 07:42，模块线：secret/撤销/无痕不生成操作或摘要；敏感/出生资料默认待单独确认。
所有批次仍需要用户审阅；不输出可绕过批准的apply接口。

2026-10-21 07:42，模块线：重放依靠host提供的operation ledger绑定input与plan指纹；
撤销候选必须有匹配的applied ledger和当前来源/版本，不能自造历史批准或复活失效来源。

2026-10-21 07:58，模块线：host的synthetic默认False，fixture必须显式True；与早期接口草案的True不同，
这是安全收紧。撤销从host ledger读取逐行实际post revision，不假设标签更新必然使message revision加一；
global applied revision必须超过所审阅快照。旧人工归区及已有关联话题不直接覆盖，转为显式冲突。

2026-10-21 08:00，模块线：identifier收紧后，“thread_id不同于host”的自测改用另一个合法opaque ID，
隔离版本匹配行为；原来使用正文作为thread_id会被更早拒绝。另有独立新增用例保护正文不能混入metadata，
没有放松任何产品断言或修改peer验收矩阵。

## Plan of Work

新增`mingjing_core/organize/export_dry_run_v3/`，不修改已有导入入口。
契约拆成contracts、codec/guards、planner、preview/undo等小文件，每文件≤400行、函数≤60行、行≤120。
可信快照保存scope、revision、source_epoch、完整messages/topics、MemorySource及operation ledger；所有JSON深冻结。
数据不因导出JSON自称owner或synthetic而可信，必须与显式host快照逐行核对。

M1输出规范化消息与原话anchor；跨owner/subject整批固定错误，其余不可用行只产生无正文冲突。
M2用Q5输出生成独立话题/标签候选。分类abstain不改成日常，不提供模型起标题路径。
M3预览只含数量、临时标题、时间范围、≤80字样例与待确认项；敏感样例默认省略。
撤销只生成逆操作及冲突，不调用任何实际store或数据库。

## Interfaces and Dependencies

`ExportSnapshot(scope, revision, source_epoch, document, sources, operations=(), synthetic=False)`是可信host当前投影，
不是自认证权限。document是完整messages/topics副本，sources来自当前来源查询。
fixture必须显式`synthetic=True`；省略或False会拒绝。

`dry_run_export(payload, *, snapshot, scope, clock, operation_id) -> DryRunPlan`

`preview_dry_run(plan, *, snapshot, scope, clock) -> dict[str, object]`

`plan_undo_dry_run(plan, *, snapshot, scope, clock) -> UndoPreview`

raw payload含schema、synthetic、export_id、scope、revision、source_epoch、messages；
每消息的id/revision/source_id/source_revision/role/content/at_ms/thread_id必须与当前host记录和来源一致。
operation_id与input/plan摘要绑定，摘要不包含可读正文。返回计划保留隐藏原始输入以便重新核对。
export/message/source/thread/operation ID限定1至200字节ASCII opaque标识，避免把原话混入公开metadata。
applied ledger含`applied_revision`与完整`target_revisions=((message_id, actual_post_revision),...)`，
缺失或版本不符时只返回冲突，不输出逆操作。
不新增依赖、API、工具注册、迁移、网络transport或自动文件扫描。

## Validation and Acceptance

依据07号M04的拒记边界、M05/M06/M07的敏感边界与P5b新增SP06“应用→撤销逐字段还原”，
本模块仅验证候选的before/after/inverse与合成快照，不冒称已执行SP06真实服务链。

验收行为包括：相同输入稳定重放；同operation换正文冲突；错owner/subject/epoch/revision拒绝；
原话和source版本不一致、撤销、无痕、secret不得成为操作或预览；assistant原文保留且不晋升事实；
abstain待整理；正常片段可产生话题/labels；缺失/null逆操作区分；撤销来源失效及并发标签变化返回冲突；
预览样例≤80字，异常/repr/公开metadata不带正文。

目标测试使用FrozenClock与显式UTC/Asia/Shanghai，不依赖东京本机时区；固定种子属性测试。
主线07:45回归只覆盖此前完成模块，新模块不进入其冻结范围；本子任务只运行一个目标pytest进程。

## Concrete Steps

工作目录为上述zhiming-v4-mod，使用已锁定Core Python与现有Ruff环境；TEMP/TMP置private/mod-week/tmp，关闭tracing并清空模型key。

    python -m pytest tests/v4/export_dry_run_v3 -q
    python -m ruff check --select E,F,I,B,UP,SIM <本阶段新增文件>
    python -m ruff format --check --line-length 120 <本阶段新增文件>

root独占Git；本agent不运行全量回归、不提交、不推送。

## Idempotence and Recovery

计算计划不改变输入或当前快照。相同operation/input得到相同指纹；host ledger若同operation绑定别的指纹则拒绝。
撤销只是候选，必须查当前源、scope、epoch、批次ledger与字段前提；有冲突不输出可直接应用的逆操作。
已撤销批次不得重新计划应用。没有真实apply，因此没有本阶段数据回滚、删除或备份操作。

## Outcomes & Retrospective

当前新增纯转换、预览与撤销候选由67自测与89独立验收合跑156项通过（2.02秒），含双方各100组固定种子组合。
Ruff format/check与类型/AST检查通过；9产品文件最大191行、最长函数56行。
产品聚合SHA256为`ae7a40dd8214197a3d383ad3e5643eb079b94302424aec4e7107964ac99bbf7c`。
final性能于07:59:50+08观测，120条中位0.2831秒/峰3608755字节，500条中位1.2482秒/峰12481694字节；
每项1预热、5观测及单独tracemalloc，源码前后hash一致。07:56旧观测保留为hardening前历史。
未实现真实导出映射、数据库应用、用户审阅服务或stage验证；没有CI/真实脚本评测证明，root后续回归与提交独立记录。
不把03至07空档记为持续开发。

## Artifacts and Notes

合成语料拟放`tools/eval/fixtures/mod_20261021/v3_export_synthetic.json`，声明synthetic，不含真人历史。
最终接线与证据拟放`docs/v4/integration/mod/P5b_export_dry_run_20261021.md`及同日evidence目录。
真实导出格式映射、stage数据副本、真人审阅、数据库应用和撤销均为未接线项。

## 修订记录

- 2026-10-21 07:42 创建：冻结离线中间格式、host来源门禁和仅候选的应用/撤销边界。
- 2026-10-21 07:58 更新：记录61项自测、默认synthetic=False、人工归区保护、实际post revision ledger与性能证据边界。
- 2026-10-21 08:00 更新：记录156项最终合测、独立验收边界、final性能和root待提交状态。
