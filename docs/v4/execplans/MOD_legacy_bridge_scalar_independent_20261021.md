# MOD：旧桥标量字段的五项独立公开输入验收

本 ExecPlan 遵循 `.agent/PLANS.md`，四活段落随真实观察更新。创建时刻 `2026-10-21T11:05:33.532131+08:00`，一律北京时间。

## Purpose / Big Picture

旧消息版本与毫秒时刻是来源身份的一部分。数值看似相等不能使JSON浮点或布尔值成为合法整数。
用五份公开合法来源及已审阅计划验证严格类型，同时证明合法版本2和UTC epoch零时刻可以继续生成仅标签ChangeSet。
ChangeSet是记录字段差异与逆操作的纯变更集，不是实际数据库写入。本轮只首测并保留结果，不修改产品。

## Context and Orientation

唯一目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
复用 `organize/supplement_v2/review.py:24` 的 build_review_proposal、`:128` 的 plan_review_labels、
公开ReviewApproval及 `legacy_bridge.py:45` 的 to_legacy_changeset；只用公开MemorySource、SourceAnchor、
EntityRecord、SupplementSnapshot构造器，合法origin=user、同scope、整句原话锚点、版本一致。
严禁调用产品私有helper、借calendar fixture或自行seal计划。

公开契约 `mingjing_core/organize/contracts.py:15,24-27` 规定：revision默认1且必须严格正整数；
at_ms必须是整数、拒bool，但没有正数下限。memory2.validation.require_int同样拒bool及float。
桥的raw dict入口没有经过Message构造；旧ChangeSet只做JSON安全、标签和来源指纹验证，不能补足字段类型契约。
`DAY_supplement_20261021.md`“主线接线工作”要求全文、角色、时刻、修订及原标签一致；
P5b SP06背景是仅标签应用/撤销逐字段还原，F03来源删除传播门禁维持，但本轮不冒称完整系统场景验收。

## Progress

- [x] (2026-10-21T11:05:33.532131+08:00) root授权精确五项；公开契约/正常链已读，五行矩阵和正文在首测前冻结。
- [x] (2026-10-21T11:08:34.663583+08:00) 独有146行测试完成；Ruff/format120、AST完整标注、最长函数48行检查通过。
- [x] (2026-10-21T11:08:35.895581+08:00) 首轮3 failed / 2 passed in0.22s原件保留，28份前后零漂移，立即报告root。
- [x] (2026-10-21T11:11:30.777806+08:00) root仅在本轮新bridge增4行严格标量守卫；完整只读复核该文件，不编辑产品。
- [x] (2026-10-21T11:11:31.864546+08:00) root授权仅复跑原五项：5 passed in0.11s；29份前后all/domain/runner drift均空。
- [x] (2026-10-21T11:13:18.865285+08:00) 最小字节审查通过：去掉新24–27四行即可精确重建原SHA；四活段落/小回执更新后冻结。
- [ ] 两套必要兼容由calendar/root另行执行，本子任务未重复或扩展；coverage、PG、CI及真实业务接线不在本任务验证范围。

## Surprises & Discoveries

首轮公开合法snapshot/审阅setup后，IB01 raw revision=1.0、IB03等值float at_ms、IB04 epoch 0 raw False均未受控拒绝。
首轮`3 failed, 2 passed in 0.22s`完整保留；IB02 int2与IB05 int0两个正例当时即通过，因此不是setup或统一拒绝造成的假缺陷。
root在新bridge._message_matches仅加4行：revision缺键取1，必须exact int且>=1；at_ms必须exact int，不加正数限制。
原五项未经修改复跑`5 passed in 0.11s`。当前文件去掉24–27行即得原SHA`e6b5a98bf95241d29470d2236b899a05bfd86615b130c13445a5529e85451c9b`，没有其他字节差异。
首轮28份和修后29份各自前后稳定；二者域源的已授权差异是bridge修复，runner工具另立范围，不混淆。

## Decision Log

精确IB01–05与calendar原15矩阵、原测试/断言保持不变，没有因首失败降低拒绝预期。
root负责唯一产品修改；本子任务只读其最小diff并按授权复跑原五项，不跑兼容/coverage或新增用例。
修复拒bool/float等非法数值类型，不做int(...)强制转换；保留缺键默认1、匹配int2及合法int0时刻。
默认1行为的实际目标由calendar原LB15保护；本五项不冒充另测了LB15或完整系统归属/撤源路径。
两次证据均绑定completed_regression.py作为环境工具；后续root合法固定材料名单更改不等于域源变化。
首轮与修后报告中的活计划SHA是各自运行时原件；2026-10-21T11:13:18.865285+08:00更新计划/回执后不回写这些历史SHA。

## Outcomes & Retrospective

本子任务完成“独立五项首失败→root最小通用修复→原五项复核”的有限闭环，最终5/5通过。
首轮3失败证据、两个合法正例和原断言都保留；21份代码/环境工具、2原测试、两矩阵及新素材/测试在各次采样内没有漂移。
修后29份含原首失败JSON；domain_source_count=20，runner工具1份单独分类，运行时两类漂移均为空。
本子任务没有产品编辑、真实模型/网络/服务器/PG/通知/Git或实际业务apply。
必要兼容由calendar/root执行，不将本五项目标冒充模块兼容、全量、覆盖、性能或CI验收。
此前10:45三轮与192产品覆盖既未包含本后补五项，也不是修后bridge源码，保持旧历史身份不改写。

## Plan of Work

先冻结五行JSON和独有合成正文，再新增 `tests/v4/organize_supplement_v2/test_legacy_scalar_acceptance_mod.py`
与独有helper。测试只接公开入口，并观察标签白名单、非空合法变更、原文档/快照保留。
运行前后绑定21份相关代码/运行器、两份原测试、calendar原矩阵、本矩阵、正文以及新测试/helper。
首失败只存证报告；必要产品修复由root统一选择和实施。

## Concrete Steps

Core Python固定为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe`。
子进程环境使用completed_regression.environment，12类provider key移除、tracing关闭、TEMP/TMP位于本树private。
显式FrozenClock使用矩阵UTC时刻；记录时刻由SystemClock转Asia/Shanghai，宿主Tokyo不参与语义。
仅单个目标进程，预期可观察结果是五项各自通过或原样失败，不通过不调整黄金。

    python -B -m pytest tests/v4/organize_supplement_v2/test_legacy_scalar_acceptance_mod.py -q --tb=short

## Validation and Acceptance

| ID | 唯一标量边界 | 固定预期 |
| --- | --- | --- |
| IB01 | 合法int1来源/实体，raw revision为数值相等float1.0 | 受控拒绝 |
| IB02 | source/anchor/entity/raw均合法int2 | 仅标签ChangeSet |
| IB03 | 正常2026原话，raw at_ms为数值相等float | 受控拒绝 |
| IB04 | 合法UTC epoch 0来源，raw at_ms=False | 受控拒绝 |
| IB05 | 同epoch来源，raw at_ms为合法int0 | 仅标签ChangeSet |

拒绝不得泄露合成正文；所有输入不变。正例不得更改正文、role、at_ms、revision等非标签字段。
本表仅五项，对应P5b SP06/F03的不变量背景，不是旧v2.1/v2.2 runner或模型评测。

## Idempotence and Recovery

文档/首测证据采用新增路径，不覆盖历史，raw日志保留不删除。无迁移、实际apply、撤回、数据删除或运行接线。
失败后保留原测试与矩阵，不能重试到隐藏首结果；修复与复测等root另行授权。

## Artifacts and Notes

五行矩阵 `LEGACY_SCALAR_frozen_matrix_20261021.json` 原始LF SHA：`7b164849815b572f2dcbc583b2718c523965df5546b4dc227f3811b4d6a7cff9`。
矩阵cases规范JSON SHA：`2543357173da255a975c00fa7edc60a1f639e1ece6fa654a65dadd8485bdb9a2`。正文fixture `tools/eval/fixtures/mod_20261021/legacy_scalar_independent_synthetic.json` SHA：`a77296ab9d19a25a79758027ced13928589b1c308ab25ebe53056def1ac15d9b`。
calendar原矩阵 SHA：`883b171aa7589aa1ee807d439c1779714ee91f588c9a2b0755b269b07b3491b2`，独立保持不变。
首测拟新增 `docs/v4/evidence/MOD_2026-10-21/LEGACY_SCALAR_independent_first_20261021.json`；目前尚不存在。
所有材料是明确合成数据，不读Q5 B或私有75正文。

## Interfaces and Dependencies

不新增产品接口或依赖，仅使用现有公开函数。ReviewApproval在本测试里是合成host可信输入，不声称真实用户授权已验证。
旧ChangeSet/MemorySource/SourceAnchor公共契约、缺revision默认1、现有owner/角色/版本/撤回/无痕/敏感/epoch等门禁均不放松。

## 修订记录

- 2026-10-21T11:05:33.532131+08:00：独立五项真值和合成素材先冻结；当前尚未新增Python或首测。

- 2026-10-21T11:10:12.253410+08:00：保留首测3失败2通过及28来源稳定证据；更新四活段落并交root，原五项真值/产品未改。

- 2026-10-21T11:13:18.865285+08:00：root四行守卫后原五项5/5；新postfix证据及严格字节diff已存，四活段落与回执重冻结。
