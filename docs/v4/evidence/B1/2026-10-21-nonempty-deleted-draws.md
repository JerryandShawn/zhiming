# B1新阻塞：非空deleted_draws在真实恢复后丢失导出

北京时间2026-10-21 09:59记录。仅本机Windows隔离PG15、固定候选b9a89b6f84f7bebb640de080548010859aae630c；未修改候选、迁移、B3/consumer/B7生产文件、旧测试或任何评分。模型/飞书/服务器/环境恢复尝试均0，未部署或合并。

新测试使用原真实proof_db：新随机source/restore与双角色、Core迁移1–4、真实Memory/Tarot seed和public checkpoint、实际pg_dump合格backup。dump后仅该测试source显式迁7，真正MemoryService.retire_fact，再以repo.mutation_request('tarot-delete:<id>')包真实TarotService.delete；receipt来自真实effect，未手插mutation receipt或拼造ledger。真实export.latest.deleted_draws明确为单个实际draw，随后调用原B3 generate，真正pg_restore→恢复4核hash→迁5–7→原apply_withdrawals。

首次按原成功要求运行节点`tests/v4/release/test_b1_restore_deleted_draws_pg.py::test_nonempty_deleted_draws_original_success_requirement`，结果**1 failed/10.07s**，session50547退出1。栈为generate→run_worker(replay)→`ReplayRejected: PINNED_REPLAY_FAILED`。原日志`private/b1-nonempty-draws-20261021/first-red.log`保留；首红时测试raw SHA256为9c24f238e6aebd6c97216b1709e8025c2eae858e6dbda49e68929be8a988dfac。

失败后实际目标观察（无正文）：

| 实际字段 | 结果 |
| --- | --- |
| schema_migrations | 精确1–7 |
| 被撤回source/fact | 两行均deleted且data={} |
| 原draw / 其run:e0 checkpoint | 均0 |
| 实际latest.deleted_draws | 1 |
| 目标再次真实export.deleted_draws | 0 |
| 目标tarot-delete mutation receipt | 0 |

第二次新随机fixture只增加直接原`verify_monotone(latest,目标真实export)`核验，明确得到**STALE_WITHDRAWALS**。最终节点`test_nonempty_deleted_draws_is_a_real_roundtrip_blocker_after_physical_erasure`：**1 passed/10.07s**，session60984退出0，无skip/xfail，日志`private/b1-nonempty-draws-20261021/blocker-probe.log`。该节点明确assert B3失败/原单调门拒绝和目标已清空；它验证阻塞存在，绝不表示B3业务可用或功能已修复。Ruff/format/400/60通过。

根因源码只读对照：固定b9 `tools/deploy_core.py.export_withdrawals`只从core_mutation_requests的tarot-delete receipt生成deleted_draws；apply_withdrawals会真实删draw、补tarot_request tombstone，却没有重建该删除receipt。B3 replay之后的原verify_monotone要求最新deleted_draws原项仍在，因真实目标导出丢失而安全停止。已清空正文/draw/checkpoint不能替代完整ledger单调契约或签成功proof。

旧B3空deleted_draws样本、旧53/55成功与ACL/USAGE目标没有覆盖此分支，其数字保持原范围。此问题与schema4源撤销缺core_embeddings表是两个独立阻塞：即使引入只迁delta副本7的设计，恢复库重新导出这个门仍然会拒绝。

待决：固定B1候选和完整账本契约应如何修复/受审，交大脑裁定。当前不删latest字段、不把原receipt假插到目标、不松verify_monotone、不修改b9或生产B3。No-Go保留，纯delta方案不能自动解除。所有测试仅清本次随机资源，未在消费后的目标上自动重跑恢复。
