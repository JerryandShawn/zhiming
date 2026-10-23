# MOD：规划记忆变更公开边界的有限验收

本计划遵循 `.agent/PLANS.md`。时间均为北京时间。先只读冻结真值，再经 root 明确放行新增测试；产品保持不变。

## Purpose / Big Picture

记忆变更计划描述一次拟保存、更新、归档或遗忘；内容指纹用于核对计划未变，不是授权签名。
本轮拟验证公开计划输入的完整性、归档不得改事实内容、遗忘后的旧操作重放不能复活数据。
以最多 24 个确定性用例补真实公开入口边界，不重复已有 1000 步生命周期属性测试。

## Context and Orientation

唯一工作目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
当前依据为 `docs/v4/evidence/MOD_2026-10-21/MORNING_completed_coverage_0945.json`。
其中 mutations.py 综合 79.1667%（64/76 行、31/44 分支）；mutation_contracts.py 为 87.3016%，
plan_builder.py 为 87.6106%，contracts.py 为 87.7934%。覆盖遗漏只提示审阅方向，不直接证明错误。

已完整读取四个目标文件及直接依赖/调用方：

| 文件（均相对本工作目录） | 复用入口或审阅目的 |
| --- | --- |
| `mingjing_core/memory2/mutations.py` | apply_plan、策略重算、重放状态 |
| `mingjing_core/memory2/mutation_contracts.py` | FactChange、MutationPlan、MutationOutcome |
| `mingjing_core/memory2/plan_builder.py` | plan_write、plan_changes、fingerprint、seal |
| `mingjing_core/memory2/contracts.py` | Scope/Source/Anchor/Fact/Snapshot/Confirmation/OperationRecord |
| `mingjing_core/memory2/guards.py`、`validation.py` | 当前原话授权、严格公开类型 |
| `mingjing_core/memory2/sensitivity.py` | 原话先行、敏感确认、Clock 与问一次策略 |
| `mingjing_core/memory2/archive.py`、`forget.py`、`undo.py` | 元数据归档、遗忘计划、逐字段撤销调用方 |
| `mingjing_core/memory2/current_guard.py`、`dedup.py`、`conflicts.py` | 当前槽位、去重合并、提案边界 |
| `mingjing_core/memory/slots.py` | 槽位 registry 与临时状态，不在本轮重测分类质量 |
| `tools/mod_week/benchmark_memory_pipeline_v2.py` | 已发布来源→保存→提醒→归档/撤销调用方式，只读不执行 |
| `tests/v4/memory2/test_mutations_mod.py`、`test_mutation_acceptance_mod.py` | 现有真值，防止重复与降级 |
| `docs/v4/integration/mod/Q2_memory2_20261021.md` | 主线权威快照/真实 Clock/PG 事务职责 |

蓝图 §6.2/§16、P5 记忆增补要求原话连续锚点、敏感先确认、助手不变用户事实、可撤销但撤源不复活。
本模块没有直接调用 PG 的生产入口；archive/forget 等只返回计划，主线仍须在权威事务中应用和保存操作记录。
主线适配必须传真实 Clock，不能把 apply_plan 默认的离线 evaluated_at 回放当当前时间授权。

## Progress

- [x] (2026-10-21 09:54 +08:00) 读取指令板 v1、最新缺口、四目标完整文件和上述直接依赖/调用方及原测试。
- [x] (2026-10-21 09:54 +08:00) 形成以下 24 项独立真值和两项仅静态疑点。
- [x] (2026-10-21 09:56 +08:00) root 明确放行；先发送原计划 SHA 与独立矩阵 SHA，再新增唯一 helper 和 24 节点目标。
- [x] (2026-10-21 09:59 +08:00) 首跑 24 passed/0.11s，无产品缺陷；21 产品/调用方前后身份一致。
- [x] (2026-10-21 10:01 +08:00) root 另行授权的一次 memory2 插桩兼容 583 passed/3.47s，实际原 559+新 24，无排除。
- [x] (2026-10-21 10:02 +08:00) 两新 Python 文件静态检查通过，21 源+15 测试/fixture 不漂移；计划、证据、接线补充与回执冻结。

## Surprises & Discoveries

mutations 的低覆盖主要来自不完整计划、before-image 不一致、特定遗忘重放和授权重算拒绝。
这些输入可由公开不可变类型/计划入口表达，无需绕过构造函数或访问私有属性。
大量当前值更新、三跳 undo、遗忘两端和随机生命周期已经有强断言，本轮不复制这些数量。
24 项首次执行全部通过，没有确认的产品缺陷；后续没有为分数补例或调整原真值。

两个静态疑点不纳入下表真值，实施前请 root 审阅口径：plan_changes 允许调用方给出归档后 revision，
未显式要求高于 before；write_status/summary 也可由调用方指定。可能涉及版本单调性和回执措辞，
也可能是可信 host 的职责。没有据此宣称可利用、擅自改变接口或写必失败金标。

## Decision Log

有限矩阵恰为 M01–M24，24 个节点，不做隐含参数笛卡尔积；若发现需要额外反例，先替换冗余项或请 root 审阅，硬上限 30。
计划重建只用公开 MutationPlan/FactChange、dataclasses.replace 和公开 fingerprint/seal；
指纹自洽并不绕过 apply_plan 的内在授权重算。禁止 object.__new__、改 frozen 对象内部或 mock 私有校验。
来源删除后的“无事实”场景使用合法 MemorySnapshot 当前投影，明确不是本模块执行物理删除的证明。
所有拒绝测试都核对输入快照未变，不要求未约定的异常正文；正例核对实际事实/来源/操作账本。
前轮保存/归档/撤销黄金及 source 撤销规则保持，不因覆盖率目标而改真值。
实施前真值正文 SHA-256 固定为 `04f34c69a7300d898c130c72e59c0c287463f18378e920b98dca82ee3ee299c0`；
仅标题和活段记录执行进度，不改矩阵正文。初始完整计划 SHA 为 `c36a33476d86cfc25b688035de7ad850711c230003e7122b0b99b6d5202db73c`。
root 只批准一次 scoped 插桩兼容，不是跨模块全量，也不能追认这些后补测试已在 09:45 回归中执行。

## 独立真值矩阵（实施前冻结，现已首跑）

| ID | 公开输入/动作 | 期望可观察行为 |
| --- | --- | --- |
| M01 | plan_write 返回的计划丢失 fingerprint 后交 apply_plan | MutationConflict；没有事实或操作记录写入 |
| M02 | 已签定当前主体的计划交另一 subject 快照 | 拒绝；双方内容与 ledger 不变 |
| M03 | 缓存计划的 summary 被改但保留旧指纹 | 拒绝内容完整性破坏；不能制造新回执 |
| M04 | plan_changes 的 before=None，尝试元数据方式新增事实 | 拒绝；metadata 不能当创建授权 |
| M05 | plan_changes 的 after=None，尝试元数据方式删事实 | 拒绝；不能借归档执行删除 |
| M06 | metadata before/after 明确 foreign owner | scope 拒绝；不回显外国主体正文 |
| M07 | metadata before/after 明确 foreign subject | scope 拒绝；原 owner 下主体也隔离 |
| M08 | metadata 归档同时改变 event_end | 拒绝改写事实时间；内容与锚点保持 |
| M09 | metadata before-image 过期，host snapshot revision 却未变 | apply 拒绝 fact_revision_changed，不覆盖当前事实 |
| M10 | 保存后经公开 plan_forget 遗忘，再重放旧保存操作 | replayed/unavailable；不恢复正文/来源 |
| M11 | 重放已经应用的公开遗忘操作，目标 tombstone 仍在 | replayed/forgotten；不再写入、不增加 snapshot revision |
| M12 | 权威当前投影已移除保存结果，只留原 operation ledger | 旧保存重放 unavailable；不从 plan 重建事实 |
| M13 | 权威当前投影已移除遗忘 tombstone，只留原 ledger | 遗忘重放仍幂等 forgotten，不重建 tombstone 或原文 |
| M14 | 重建指纹自洽但 incoming=None、policy_action=save 的公开计划 | 拒绝缺少授权来源；hash 不等于权限 |
| M15 | 公开写入计划重建时缺 evaluated_at | 拒绝缺策略时间，不用本机当前时间猜填 |
| M16 | 公开 plan 声称 forget 却没有 deleted 目标 | forget_plan_invalid；不产生遗忘回执 |
| M17 | 合法遗忘计划夹带邻居正文改写并重新计算指纹 | 重算与权威 plan_forget 不同而拒绝，邻居正文不变 |
| M18 | FactChange.id 与 before/after 的事实 ID 不同 | 公开构造即拒绝，避免错实体覆盖 |
| M19 | host 反序列化 MutationPlan 时 scope 不是 MemoryScope | 公开构造拒绝，不隐式转换归属 |
| M20 | MutationPlan.incoming 是普通 dict 而非 MemoryFact | 构造拒绝，不能跳过事实类型/锚点边界 |
| M21 | MutationPlan.confirmation 是普通 dict 而非 Confirmation | 构造拒绝，不能将用户/模型 JSON 直接当确认 |
| M22 | MemorySettings.auto_save_categories 是单个字符串 | 构造拒绝；不能逐字符展开成长期授权 |
| M23 | 合法 assistant_claim note 原话被夹入重建 save 计划的 changes | apply 拒绝助手来源变用户事实，不依赖调用方许可布尔 |
| M24 | 真实有效来源的元数据归档→apply→undo | 正例通过；所有事实内容字段逐字段还原，来源状态未被撤销/删除 |

## Outcomes & Retrospective

24 项固定真值首次全部通过，完整 memory2 scoped 兼容为 583 项，实际原 559 加新 24。
四目标总行 365/385=94.8052%、分支 103/124=83.0645%、综合 468/509=91.9450%。
mutations.py 综合 95.8333%，mutation_contracts 100%，plan_builder 91.1504%，contracts 87.7934%。
总分支仍不足 90%，公开 JSON 保留逐文件 missing_lines/branches，不宣称所有风险已关闭。
没有产品改动、旧测试/黄金改动或真值调整，没有真实模型/网络/PG/通知/运行态写入。
两个静态疑点仍待主线/大脑裁定，未转成新政策或必失败断言；真实事务和 CI 未验证。

## Plan of Work

实际新增 `tests/v4/memory2/mutation_boundary_support_acceptance_mod.py` 和
`test_mutation_boundary_coverage_acceptance_mod.py`，全部显式虚构文本、明确 SourceAnchor 和 FrozenClock。
每节点独立计划/快照，无模块级可变 Clock，不读 Q5 B 或校准 75 条材料。
先目标后 root 决定的有限兼容；任何真实失败先保存 source/fixture/test SHA，不先修产品。

## Concrete Steps

已在本目录使用既有 Core 解释器执行下列目标命令，后续重跑须由 root 协调：

    python -m pytest tests/v4/memory2/test_mutation_boundary_coverage_acceptance_mod.py -q --tb=short

provider keys 清空、tracing 关闭、socket 禁止，TEMP/TMP 在本树 private/mod-week/tmp。
每 agent 最多一个测试进程；完整回归、覆盖和任何产品修复都需 root 明确协调。

## Validation and Acceptance

关联 07 场景 M04/M05/M12、F01/F02/F03 的拒记、敏感确认、真实回执和遗忘不复活约束。
本轮只验证纯变更边界，不宣称数据库级助手事实计数、索引级联删除、真实 action token 或前端回执已验证。
M24 是必要正对照，避免把一律拒绝误判为安全；M10–M13 核对真实返回状态与快照恒等，不只核字段存在。
24 项矩阵不承诺覆盖所有 missing 行，覆盖只作为实际行为执行的证据。

## Idempotence and Recovery

全部进程内输入可重复，失败时不变更金标。后续证据写 `MEMORY_mutation_boundary_*` 新文件，旧报告保留历史。
若跨续作，断点为“24 项目标与单次 583 scoped 兼容已完成并冻结，产品不变，两个静态疑点待决”。

## Artifacts and Notes

审阅源为 MORNING_completed_coverage_0945.json，保留历史。
24 项首跑证据 `MEMORY_mutation_boundary_initial_20261021.json` SHA-256：
`acf47888647ab51a8102de09abb6e6bd7b3e059c34a18897cf826e9b434df19c`。
单次 scoped 兼容覆盖证据 `MEMORY_mutation_boundary_coverage_20261021.json` SHA-256：
`a7fdf3ad1954056563f4d8661f1b65032efc49741d43c95a5b139a9bcef82399`。
新接线补充为 `docs/v4/integration/mod/MEMORY_mutation_boundary_20261021.md`。
后续实际结果与 §11 回执必须分开写明：本地目标、PG/CI、真实运行与未完成状态。

## Interfaces and Dependencies

没有新增产品接口、Schema、依赖、运行配置、数据库迁移或自动化。本子任务不执行 Git。
权威快照和 operation ledger 的真实事务、提交前再次核源仍由主线提供，内存 apply 不能自证数据库当前性。

## 修订记录

- 2026-10-21 09:54 +08:00：创建；完成实际覆盖缺口、完整文件与调用方审阅，冻结 24 项计划，等待 root 明确放行。
- 2026-10-21 10:02 +08:00：记录放行后的 24/583 通过、实际四文件覆盖和未裁定静态口径，冻结成果。
