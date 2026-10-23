# B1 schema4 seed：本机通过范围与真实撤销阻塞

北京时间2026-10-21 09:50创建，09:51冻结。本片为独立本机能力探针，绝不构成Linux演练通过、正式B2/B3证明、B7、stage Go或授权B/D执行。源代码候选始终固定`b9a89b6f84f7bebb640de080548010859aae630c`，manifest raw SHA256为`49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`；未修改候选或迁移1–7。独立计划为`docs/v4/execplans/B1_schema4_seed_20261021.md`。

## 实测结论

真实本机Windows PostgreSQL15，端点仅回环55480，新随机`b1_application_<32hex>`数据库和独立非系统owner/writer角色。每库只初始化固定候选迁移0001–0004，所有候选repo都显式`initialize=False`。实际`LangGraphRuntime(repo)`成功建立四张public checkpoint表；实际MemoryService.receive/save_fact/create_case、TarotService.create_draw、begin_run/fail_run与真实PostgresSaver.put成功。checkpoint包含一条记录和一个真实序列化blob，Core ledger始终精确1–4；实际export_withdrawals可以导出完整两owner与原sent/uncertain两条保护收据的初始账本摘要。

真实`MemoryService.retire_fact(...scope='source')`失败：`UndefinedTable`，经过固定表名白名单诊断投影为`SEED_PINNED_UNDEFINEDTABLE_CORE_EMBEDDINGS`，无DSN、SQL正文、私人异常文字。固定候选`mingjing_core/repositories/privacy_foundation.py:93–120`无条件删除迁7才有的core_embeddings；受影响run还会涉及迁5的core_run_steps/core_run_events。因而原source保持4时无法从此候选生成最新撤销delta。这是固定B1架构前提的阻塞，不能靠提前迁7或补改候选掩盖。

该失败前后的完整Core+四checkpoint表canonical state hash相同，私有快照逐字段相同，Core仍1–4；source/fact仍active、draw仍存在、原两保护收据不降级、新两pending仍pending、模型charge为0。Tarot删除、新收据状态改变和最新ledger导出在失败之后没有继续。没有手删checkpoint来制造清理成功，也没有手填账本。

## 精确验证范围

默认CLI不带`--apply`只打印计划，0连接。显式子进程使用独立候选Python3.11、`-I -B -X pycache_prefix=<absolute os.devnull>`，清供应商凭据/飞书与追踪；候选manifest及所有成员hash、实际导入路径逐项核查。

PG门核实际版本/端口/库/角色、独立owner/writer无系统权限或membership、database owner、无其它client/活动run、精确表集合/Core1–4。纯fixture拒额外owner/实体/原话、变更原run/保护收据、未知或抬高的core_versions、篡改source/fact lineage/operation fingerprint、伪或错阶段receipt、错规范/旧state/额外字段；即使重算外层state hash也不能给这些变化授权。业务写前另在同一事务锁住所有Core表并重核。

精确版本集合只有`(primary,global:self)=1`和`(primary,case:<本次seedcase>)=2`。原两message和secondary保持原样；原成功run补固定合成answer，request同时固定source_message_id与`message==synthetic original`，符合b9 backfill._run_context的真实必要条件，未执行后续回填。

draw由固定b9真实创建后，其随机ID/request与完整state绑定实际seed回执；控制器不接受任意expected_rows。当前未逐字段验证整个随机牌序、所有draw payload字段的canonical内容，故只用于受控local UUID库能力探针；不能宣称共同profile已可生产放行。更深draw证明与后续App桥待独立批准。

## 测试与历史

专属命令（Core Python3.11，先清凭据，TZ=Asia/Tokyo、追踪关闭，仅显式本机测试admin DSN）：

    python -m pytest tests/v4/release/test_b1_bootstrap_replay_seed_contracts.py tests/v4/release/test_b1_bootstrap_replay_seed_pg.py -q --tb=short

最终固定当前六件源码/测试：**34 passed/106.63s**，14纯契约+20真实随机PG目标，0skip/xfail/warning。session98100退出0，实际完成复核北京时间09:51；日志`private/b1-schema4-seed-20261021/target-after-legacy-intent.log`。Ruff(E/F/I/B/UP/SIM)/format绿，各源码行数399/141/374/88/118/143，最大函数49行。此34绿表示本机seed边界和schema4撤销原子失败被证实，绝不表示撤销业务可用。

历史中期WIP组30 passed/106.15s；补精确version等反例后34 passed/109.33s，其日志`private/b1-schema4-seed-20261021/target-final.log`独立保留。之后只修正合成legacy run的真实message输入以避免未来空回填，最终按固定当前源码重跑整个专属组，不回签此前数字。

首轮controller自身误把同一时刻的+09/+00字符串不同视为拒绝，另有source/message operation键名与primitive checkpoint未产生blob两处校验错误；均已修正，不把这些当候选问题。独立真实候选撤销首红为原节点`test_actual_b9_schema4_checkpoint_business_withdrawal_and_export`的`SEED_PINNED_UNDEFINEDTABLE_L304`（PG驱动抛错行），后续改为明确能力节点`test_actual_schema4_seed_and_export_but_withdrawal_is_atomic_candidate_blocker`，无xfail/skip/篡改业务结果：断言失败及原子状态保留，仅表示阻塞已复现。

## 未验证与下一步

未运行真实Linux、Docker/WSL新探测、任何SSH/stage/生产、模型、飞书或发送器；全部为0。未生成合格B2备份，没有B3/B7总链、source升级/回填、delta副本、跨exec fence或正式权限证明。本工具phase=withdraw仅为当前必然失败的能力探针，不可用于stage撤销。setup/put可能各自已提交，seed整体不声称全原子；生产工具失败保留该随机库现状，不自动覆盖/重跑，pytest只回收自己创建的随机资源。

下一片只写独立delta克隆设计：source4在B2/B3前保持4；最新撤销必须在另受审同dump/同ID的独立delta副本迁7后用真实业务产生，再讨论恢复target与最终source一致性。未获实现批准前不建delta数据库、不做其流程，不把本机证据扩成stage授权。
