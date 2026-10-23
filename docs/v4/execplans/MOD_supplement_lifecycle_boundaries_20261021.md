# MOD：整理补充模块的 9 项生命周期与授权边界

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`；四个活段落必须按后续真实授权与结果维护。
创建时间：`2026-10-21T11:32:58.244915+08:00`（Asia/Shanghai）。当前只允许新增本计划及冻结 JSON，不允许 Python、探针、测试或代码格式化。

## Purpose / Big Picture

在已有 529 项整理兼容基础上，只计划九个尚未直接验证的公开业务边界：应用账本、并发版本、人工编辑、
主体隔离、话题及目标来源删除、话题活动时间和明确目标语义。
测试意图是保证旧审阅不会覆盖当前状态或把已失去原话依据的候选当作授权，而不是追逐覆盖数字。
本轮没有运行这些案例；11:45 全量冻结继续有效，未来实施须 root 再明确放行。

## Context and Orientation

唯一工作目录：`C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
当前已完整读两套全部五个 Python：organize_supplement/test_supplement_mod.py 及 organize_supplement_v2 的
原独立测试、原15测试/helper、独立5测试；全部摘要在 JSON 固定，不修改旧真值。
完整读 projection.py、lifecycle.py、guards.py，再对照 529 的限定覆盖逐行/分支残余筛选本九例。

复用现有公开函数：`supplement_v2/projection.py:125` project_plan、`:149` project_undo；
`lifecycle.py:34` plan_topic_archive、`:125` propose_case_upgrade；
`guards.py:133` entity_from_fact；review.py 的 build_review_proposal/plan_review_labels。
它们位于 `mingjing_core/organize/`。事实投影使用 `mingjing_core/memory2/contracts.py` 中的
MemoryFact、MemorySnapshot、MemorySource、SourceAnchor，以及 timekit.clock.FrozenClock。
不调用私有验证函数、不重 seal、更不绕过冻结 dataclass。

变更账本是记录某个 operation 是否确实已应用的状态；审阅计划自身不能证明已执行。
实体 revision 表示当前实体修订，source revision 表示原话修订，两者须分别核对，不能混为同一编号。
当前宿主投影是主线从权威数据提供的合法快照；本模块的类型或指纹不能替代真实用户/数据库授权。

设计依据为 `22_功能区设计_对话与记忆分区.md` §1 的话题/事项定义和14天无新消息归档，
P5b A.5/A.7/B.7/E 的审阅、逆操作和来源传播，以及 DAY_supplement_20261021.md 的当前来源、
全局并发保守冲突及明确目标规则。AGENTS§5 的 owner 隔离、原话溯源和撤销不变量保持。

## Progress

- [x] (2026-10-21T11:32:58.244915+08:00) root 接受 S01-S09 候选，只放行两文档冻结。
- [x] 完整核对两套五个 Python 和三份产品源，排除重复、类型镜像及需伪造内部坏态的路径。
- [x] 固定九例公开 setup、精确预期、不重复依据、当前21源/5测试/4历史输入的原始字节摘要。
- [ ] root 在全量结束后接纳排期并明确放行 Python 实施；当前没有实施授权。
- [ ] 获授权后新增唯一独立测试/helper及允许位置的 synthetic fixture，不改变九例或原黄金。
- [ ] 单目标首测先保存真实失败/返回、BJT和前后摘要，再报 root；未经授权不修产品或扩测试。
- [ ] 后续本地证据、Ruff/AST、四活段落与 §11 回执按真实观察更新后冻结。

## Surprises & Discoveries

最新限定覆盖三产品的缺失路径大部分需要手造重复 ops/guards、缺 reviewed 对象、非法字段或重 seal 坏计划才能触发。
这些不是本轮优先候选，不为提升比例而制造不可达状态。九例仅使用公开业务数据及自然操作顺序。
S02 特别以真正公开 B 计划推进版本；S03 特别先经当前事实授权投影，不能仅替换对象内部 revision 冒充人工编辑。
目前没有探针、测试或新缺陷结论。

## Decision Log

保持原9例而不扩展为10例或更多；不重复 memory24/calendar28/brief30+8/CLI8、旧15+5或既有529真值。
S02 两计划不同 operation_id，分别只改 A/B 标签；source_epoch 不因标签操作假造变化，直接用 project_plan(B) 的返回值。
S03 新旧 fact 都须 owner/subject、source_ids、原话 anchors、said_at、有效期和 recorded_at 合法，
以公开 entity_from_fact 完成当前授权；当前摘要编辑及实体修订由可信宿主投影，不能绕过 Q2 授权。
S05/S08 删除只是宿主当前来源集合不再包含该条的内存场景，不实际删除数据，也不复活旧来源。
S06 是来源与生命周期的公开逻辑关系失配，类型、原话和版本本身都合法；不是绕 dataclass 的私有态。
S04 只固定受控领域拒绝而不发明新错误码。所有拒绝不得包含合成正文，不修改任何输入。
活文档及可能被 root 其他工作追加的 runner 不作为不可变域源；本 JSON 不包含它们的 hash。

## Outcomes & Retrospective

当前仅完成可复核的文档冻结，两份新文件均为 UTF-8 LF。没有新增或改动 Python、产品、旧测试或正文 fixture。
21 个相关产品、两套5个 Python 和4个既有冻结/合成输入已记录哈希；这些不是新测试通过证明。
九例尚未实施、运行或验证；没有新 coverage、性能、PG、真实模型、网络、飞书、Git 或 CI 结论。
后续实施及首轮运行必须 root 再次放行，不能因本计划存在而自行解冻代码。

## Plan of Work

文档里程碑是本次冻结：JSON 含每例公开 setup、原不重复依据、固定拒绝和当前字节摘要。
未来若 root 放行，拟只新增 `tests/v4/organize_supplement_v2/test_lifecycle_calendar_mod.py` 与独有 helper。
合成正文只允许新的 `private/` 或 `tools/eval/fixtures/` synthetic 文件，本轮不创建任何正文。
设置合法正向公开数据，使每个负例确实验证所列边界，而非用无关敏感、scope、时间或 anchor 错误替代预期。
第一次运行失败必须保留原始观察，立即报告 root，不修改黄金、放宽断言、回填历史或擅自修产品。
兼容、覆盖、性能或全量均不随单目标运行自动授权。

## Concrete Steps

当前只可校验两文档的 LF、JSON 结构、冻结 cases SHA 和受保护文件摘要；以下未来命令当前不得执行。
未来获明确放行后，使用 Core Python 3.11、runner.environment 清12类密钥与关 tracing，
临时目录保持工作区 private/mod-week/tmp；socket 类保留，只封连接出口；本代理最多一个 pytest 进程。

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -B -m pytest tests/v4/organize_supplement_v2/test_lifecycle_calendar_mod.py -q

所有 Clock 与时刻明确 aware，固定 Asia/Shanghai，不能依赖本机 Tokyo。新增 Python 仍按400/60/120与类型标注规范。

## Validation and Acceptance

`docs/v4/07_评测场景集.md` F03 的来源删除传播作为 S05/S08 背景不变量；本轮不声称完整 F03 系统验收。
P5b SP06 的逐字段还原作为 S01/S02/S03 的背景：逆操作不能越过账本或覆盖当前已批准内容。
以下九例均固定受控拒绝，不返回投影/归档候选/升级意图、不改输入，错误不回显合成正文，外部 effects=0。

| ID | 公开业务边界 | 预期 |
| --- | --- | --- |
| S01 | 从未应用的获批计划不能撤销 | operation_not_applied |
| S02 | 另一真实公开批次推进版本后旧计划不能初次应用 | snapshot_revision_changed |
| S03 | 人工编辑 fact 后旧整理计划不能覆盖当前实体 | record_evidence_changed |
| S04 | 合法 A 主体计划不能投到合法 B 主体当前快照 | 受控领域拒绝，不预设新错误码 |
| S05 | 话题原话源已删除时不能继续产生归档候选 | topic_source_required |
| S06 | 话题 last_at 落后于已包含原话来源时不能按旧闲置时间归档 | topic_last_at_precedes_source |
| S07 | 工作时钟落后于最新话题活动时受控拒绝 | topic_last_at_in_future |
| S08 | 话题仍有效但目标原话已删除时不能升级事项 | goal_source_missing |
| S09 | 普通肯定事实不能被自动推断成升级目标 | explicit_goal_required |

### S01：从未应用的获批计划不能撤销

公开入口：`project_undo(snapshot, plan, scope=scope)`。

使用当前合法原话来源、fact 实体、显式 Prediction 和公开审阅 API 取得合法 plan P；不调用 project_plan；snapshot.operations 仍是合法初始空账本；直接以原 snapshot、原 P 调用公开 project_undo。

独立依据：P5b A.5/A.7 可撤销变更集依赖真实应用账本；不能凭计划虚构已应用状态。

不重复依据：现有 preview/replay/undo 和随机标签测试都先 project_plan，再 project_undo；无撤销未执行批次。

当前出处：`mingjing_core/organize/supplement_v2/projection.py:149-153`。

### S02：另一真实公开批次推进版本后旧计划不能初次应用

公开入口：`project_plan(current_after_B, plan_A, scope=scope, approval=approval_A)`。

初始同一合法 snapshot 有独立实体 A/B 及其各自当前合法来源；两实体均非敏感；分别通过公开审阅 API 建立只改 A 的 plan_A 与只改 B 的 plan_B，使用不同 operation_id；先真实调用 project_plan(snapshot, plan_B, approval_B) 得到 current_after_B；不 replace revision、不造 operations；用返回的 current_after_B 原样尝试 plan_A。

独立依据：接线指南第31-33行：审阅绑定快照 revision；全局并发变动采取保守冲突。

不重复依据：已有标签计划创建时 staleness 和 undo 时 revision 变化；未测另一个合法公开批次推进后初次 project_plan。

当前出处：`mingjing_core/organize/supplement_v2/projection.py:125-140`。

### S03：人工编辑 fact 后旧整理计划不能覆盖当前实体

公开入口：`project_plan(current_snapshot, old_plan, scope=scope, approval=old_approval)`。

创建合法 MemoryFact/MemorySnapshot，source_ids/完整原话 anchors/scope/said_at 与当前 source 一致；先调用公开 entity_from_fact(..., clock=FrozenClock) 获得初始 fact EntityRecord，建立已审阅 old_plan；宿主当前投影以公开合法 MemoryFact 表达同一 fact 的人工摘要编辑，revision 推进且 edited=True；原话来源、锚点和 scope 不变；current fact 仍合法有效、已记录且 recorded_at<=clock.now；再次经 entity_from_fact 当前授权检查获得 current EntityRecord；以当前合法 SupplementSnapshot 提供该投影及推进后的全局 revision，再尝试旧 plan；不绕过 Q2 authorize_fact。

独立依据：接线指南审阅绑定实体内容/版本及原话；人工当前编辑不能被旧整理审阅覆盖。

不重复依据：已测 source revision、人工标签变化和计划创建时 entity revision；未测实体自身人工摘要/修订变化后的旧计划投影。

当前出处：`mingjing_core/organize/supplement_v2/guards.py:133; projection.py:48-66`。

### S04：合法 A 主体计划不能投到合法 B 主体当前快照

公开入口：`project_plan(snapshot_B, plan_A, scope=scope_B, approval=approval_A)`。

分别以公开类型构造 A/B 两套独立且内部 owner/subject 一致、来源合法的当前 snapshot；仅以 A 的公开审阅 API 取得合法 plan_A/approval_A，不修改任何获批字段或指纹；将完整 A 计划误送 B 的公开投影入口，调用 scope 明确为 B。

独立依据：AGENTS§5 owner 隔离及指南 authenticated owner/subject；A 的批准不能授权 B 数据。

不重复依据：已有 approval/grant 错主体和旧文档错归属；未测整份合法计划跨主体误投。

当前出处：`mingjing_core/organize/supplement_v2/projection.py:23-26`。

### S05：话题原话源已删除时不能继续产生归档候选

公开入口：`plan_topic_archive(current_snapshot, scope=scope, clock=clock, operation_id=operation_id)`。

话题原先有合法当前来源与完整 SourceAnchor；其余 owner/subject、TopicRecord 类型和时间均有效；宿主来源删除后的当前公开 snapshot 不再包含该 source，话题投影仍带旧 anchor，source_epoch 如实推进；只表示删除后的内存输入，不执行任何真实删除；调用公开归档候选入口。

独立依据：07 F03 来源删除传播、当前原话来源授权；派生话题不能在源消失后凭旧 anchor 获授权。

不重复依据：已测 entity source 的 revoked/active 等标志；未测话题锚定源已从当前集合消失。

当前出处：`mingjing_core/organize/supplement_v2/guards.py:88-94`。

### S06：话题 last_at 落后于已包含原话来源时不能按旧闲置时间归档

公开入口：`plan_topic_archive(snapshot, scope=scope, clock=clock, operation_id=operation_id)`。

当前话题有两个合法同主体用户来源及精确 anchors，所有来源都早于显式 Clock；TopicRecord.last_at 比其中较新来源时刻早1微秒，类型、scope、来源版本及原话均合法；表示宿主生命周期投影与来源时刻不一致，不修改冻结对象内部状态或假造私有字段。

独立依据：22号§1话题14天无新消息才归档；指南要求同事务投影完整话题生命周期，不能以落后的 last_at 忽略已包含消息。

不重复依据：已测新消息使旧 archive proposal 失效；未测生成候选前话题生命周期与其原话时刻自相矛盾。

当前出处：`mingjing_core/organize/supplement_v2/guards.py:109-110`。

### S07：工作时钟落后于最新话题活动时受控拒绝

公开入口：`plan_topic_archive(snapshot, scope=scope, clock=clock, operation_id=operation_id)`。

来源合法且早于 Clock；TopicRecord.last_at 比 FrozenClock.now 晚1微秒，来源仍不晚于 last_at；显式 aware instant 和 Asia/Shanghai，模拟工作时钟落后或记录未来活动，不依赖主机 Tokyo 时区；调用公开归档候选入口，不把未来活动误当已闲置时间。

独立依据：14天闲置必须依据有效当前时钟与已发生的最后活动；不能以未来活动构造已知归档状态。

不重复依据：已有满14天前后边界；没有 last_at 位于当前工作时钟未来的公开归档输入。

当前出处：`mingjing_core/organize/supplement_v2/lifecycle.py:47-48`。

### S08：话题仍有效但目标原话已删除时不能升级事项

公开入口：`propose_case_upgrade(current_snapshot, topic_id, stale_goal_anchor, scope=scope, clock=clock, operation_id=operation_id)`。

话题自身当前来源 T 持续合法；另有合法明确目标来源 G 和精确 goal_anchor；宿主当前公开 snapshot 保留 T 和合法话题，但删除 G；调用者仍携带此前的 G anchor，source_epoch 如实推进；不执行真实删除，不把目标替换成话题原话；调用公开升级意图入口。

独立依据：接线指南明确目标必须来自当前用户原话，实际使用前重核目标、来源与话题版本；来源删除不得复活。

不重复依据：已有目标 anchor revision 错误、否定/条件目标；未测目标源缺失而话题自身仍可授权。

当前出处：`mingjing_core/organize/supplement_v2/lifecycle.py:139-141`。

### S09：普通肯定事实不能被自动推断成升级目标

公开入口：`propose_case_upgrade(snapshot, topic_id, fact_anchor, scope=scope, clock=clock, operation_id=operation_id)`。

以显式 synthetic 的普通肯定事实建立当前合法用户来源和精确 anchor，无否定、条件、引号、敏感或秘密；话题保持 open、来源/时间均有效；事实语义不表达目标、愿望或行动意图；不调用模型推断隐含目标；直接调用公开升级意图入口。

独立依据：22号事项=有目标的话题；接线指南要求当前用户明确目标，不从普通事实自动推断目标。

不重复依据：已有肯定目标、否定及条件目标；未测无目标含义的普通肯定陈述。

当前出处：`mingjing_core/organize/supplement_v2/lifecycle.py:152-153`。

## Idempotence and Recovery

本轮仅新增文件，目标路径已有则拒绝覆盖；没有迁移、回填、真实删除、写库或运行账本变动。
未来测试用独立内存输入，公开 B 计划产生的内存状态只用于该次测试，重跑不影响真实资料。
当前 source/revocation/incognito 和敏感同意门禁不可为了通过而关闭；已删除来源也不能为 undo 重新注入。
真实反例留 first 证据，root 修复后若获授权另写 post，不覆盖原失败或旧源码摘要。

## Artifacts and Notes

冻结矩阵：[SUPPLEMENT_lifecycle_frozen_matrix_20261021.json](../evidence/MOD_2026-10-21/SUPPLEMENT_lifecycle_frozen_matrix_20261021.json)。
原始 UTF-8 LF SHA256：`82f0db4263b5055de074d4e2c899e9df23149a0dd54fc475e57e80161a1e68b3`；cases canonical SHA256：`544b38ac3e4e2fa5c2feda05f06fc20ec3f4968878783c496889c1618b280782`。
这些是内容摘要，不是 Git commit，不证明数据库当前授权。
历史限定覆盖为 `docs/v4/evidence/MOD_2026-10-21/LEGACY_BRIDGE_compatibility_coverage_20261021.json`，
SHA `49419da399476a6cc28ee9f12360014aa24d2754400744034a24880eb672abda`，529通过和九产品87.7958%综合仅是既有历史，不含本九例。
当前不新增首测或回执结果文件，root 独占 Git。

## Interfaces and Dependencies

无新增/修改产品接口、路由、表、迁移或依赖。未来 setup 只复用公开类型和已发布函数。
S03 的当前 fact 使用与 current MemorySnapshot 精确一致的原话与版本，entity_from_fact 的成功只是测试输入合格，
不能被当作摘要自然语言蕴含、真实人工身份或保存授权的证明。
S02 必须验证 B 操作确实成功、A 源与实体未被 B 改动，再验证 A 的旧全局审阅失效；不拿 replace(revision=...) 代替业务流程。

## 修订记录

- 2026-10-21T11:32:58.244915+08:00：按 root 仅文档授权新增计划和九例矩阵；锁定公开 setup、当前摘要及未运行状态，保持11:45全量代码冻结。
