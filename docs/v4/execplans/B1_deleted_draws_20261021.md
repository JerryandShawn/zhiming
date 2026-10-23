# B1：非空deleted_draws真实恢复反例

本ExecPlan遵循`.agent/PLANS.md`。北京时间2026-10-21 09:56创建，09:59更新；本片只新增独立测试和证据，不改B3/consumer/固定b9/旧53目标，不建delta实现或改源4候选。不连接服务器/模型/飞书，不再探WSL/Docker。测试只复用真实随机proof_db，PG15回环55480、清凭据/TZ=Asia/Tokyo；至多1窄进程，root统一提交。

## Purpose / Big Picture

只读发现：固定b9真实tarot-delete mutation receipt会让export_withdrawals.deleted_draws非空，但apply_withdrawals未见在恢复库重建该receipt。B3在实际重放后会把latest与目标再次导出的ledger做verify_monotone，可能因此拒绝。需用同一schema4 dump、真实源7业务和真正B3 restore复现；首次要求成功路径直接运行，真实红后才收口成明确阻塞探针。绝不手填ledger、假insert receipt、放宽验证或把目标已删除当proof通过。

## Context and Orientation

复用`tests/v4/release/b1_restore_proof_support.py`的proof_db/initialize4/backup/write、旧`tests/test_b1_restore_replay_pg.py`固定SEED常量、原tools.b1_restore_proof.generate，以及固定candidate的repo.mutation_request/TarotService.delete/MemoryService.retire_fact/export_withdrawals。candidate仍b9a89b6f84f7bebb640de080548010859aae630c，manifest49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c。source初始化4并先dump；仅已有测试source副本随后显式迁7生成latest，不对source4兼容性回签。

## Progress

- [x] root批准仅新test_b1_restore_deleted_draws_pg.py与独立计划/证据，先实际成功要求首红。
- [x] (2026-10-21 09:56 +08:00) 真schema4 seed/dump，源显式迁7，真实mutation包Tarot.delete后确认实际非空deleted_draws=1；原B3成功要求真实1 failed/10.07s，PINNED_REPLAY_FAILED，原日志保留。
- [x] (2026-10-21 09:57 +08:00) 原verify_monotone(document,真实target export)确认STALE_WITHDRAWALS；明确阻塞探针1 passed/10.07s，仅表示缺陷复现/无复活状态得到验证，不能说B3可用。
- [x] (2026-10-21 09:59 +08:00) 目标实际Core1–7、实体deleted/空、draw0/checkpoint0，latest deleted_draws1→export0、mutation_receipt0；冻结新3件tests/plan/evidence，Ruff/format/400/60绿。测试槽释放，10点不再开目标。

## Surprises & Discoveries

静态疑点已经真实PG确认。原direct Tarot.delete样本可能只有tarot_requests tombstone，未带deleted_draws，旧成功不覆盖本分支。原B3进程边界把内部失败投影PINNED_REPLAY_FAILED；失败后读取真实目标与实际export，再调用未修改的原verify_monotone确认STALE_WITHDRAWALS。候选没有重建tarot-delete mutation receipt，export的deleted_draws从最新1变0，虽然实体/draw/checkpoint实际已清空，仍然不能签B3proof。

## Decision Log

root要求先真实原成功要求红，再明确阻塞；所有PG内容只合成。新测试只在自身随机source/target读取/写受审资料，使用真实固定候选与受保护-I/-B/null pycache prefix子进程，无网络客户端/模型/发送器。

2026-10-21 09:59 +08:00 / root与Codex：保留原成功要求首红和目标无复活差异，最终测试命名为is_a_real_roundtrip_blocker，明确assert原B3失败与单调校验拒绝，不加xfail/skip、不更改旧53/55或ACL/USAGE断言。既有成功不覆盖本分支，候选真实阻塞写待决，大脑裁定前不补假receipt、松门或改b9/生产B3。

## Plan of Work

先实际初始化4/固定SEED/合格backup，保存dump/原账本；用同candidate初始化False后显式initialize向前迁7，再真正retire_fact与mutation_request包实际Tarot.delete，真实export并核deleted_draws正好该draw。原B3 generate恢复原dump→迁7→重放，首次不捕捉失败而保留红。finally只读目标身份、版本、实体/draw/checkpoint删除与真正export，以安全计数输出，不回滚或自动清目标，pytest最后仅清自己随机资源。

## Validation and Acceptance

对应07场景R02/F01来源撤销/旧历史不复活。成功条件原本要求B3 produce local proof及deleted_draws单调；如果实际不成立，验收结果是明确未完成，测试探针只能证明故障/安全停机已复现。不得使用xfail/skip、假JSON或变更旧安全断言去宣业务绿；原53组通过保留原范围。

## Idempotence and Recovery

每次独立随机两库/双角色，先真实dump再业务删除；失败不在同目标重跑B3、不自动改表/补receipt。测试只清自己创建的资源，工具不改。公开日志只固定error code/计数/状态，无正文、DSN、口令或牌序。

## Outcomes & Retrospective

真实首红`test_nonempty_deleted_draws_original_success_requirement`，1 failed/10.07s、PINNED_REPLAY_FAILED；日志`private/b1-nonempty-draws-20261021/first-red.log`，当时测试raw SHA9c24f238e6aebd6c97216b1709e8025c2eae858e6dbda49e68929be8a988dfac。最终明确阻塞探针`test_nonempty_deleted_draws_is_a_real_roundtrip_blocker_after_physical_erasure`，1 passed/10.07s，日志blocker-probe.log，直接原verify_monotone确认STALE_WITHDRAWALS。没有功能修复；完整B1链继续阻塞，纯delta方案也不能绕过此门。等待大脑裁定，root统一提交，不改任何授权。

## 修订记录

- 2026-10-21 创建：只测试/文档，非空deleted_draws原成功要求首红，保护固定候选与B3门，记录与schema4源阻塞为独立问题。
- 2026-10-21 09:59 +08:00 记录真实首红/目标领域状态/直接单调校验失败及明确阻塞探针；不把探针绿当业务修复，释放测试槽，转纯计划。
