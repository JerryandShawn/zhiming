# 已提交工具效果、未确认 Journal 的恢复证据

记录时间：2026-10-21 02:04（北京时间 UTC+08）。这是本机隔离 PostgreSQL 与离线模型替身的结果，真实模型请求、飞书发送、服务器访问均为 0；没有部署或合并。业务源码由主代理维护，本片仅新增测试、支持与文档。

## 验证方法

`tests/v4/agent/test_tool_effect_recovery_matrix_pg.py` 使用实际 AgentRuntime、ToolRegistry、应用工具、PG 实体、core_mutation_requests 与 core_operations。模型使用 ScriptedPort；既有夹具拒绝 HTTP 与子进程，并冻结时钟。只在目标工具的真实业务事务退出后、Journal.complete 确认前恰好一次抛出 SystemExit，原输出与收据来自实际工具，未生成数据库替身结果。

可同 epoch 恢复的分支只将旧 lease 设为过期，再取得同 epoch 新 lease。恢复前后逐字段比较全部相关业务实体、原 mutation 收据、operation 行与原 source；要求同一 seq/operation_id 的 started 空步骤最终完成，输出等于崩溃时实际输出，首模型步骤重放且只请求最后一条新模型回答，最终只有一个 assistant/final。

真实 memory_update 更正单列：旧 fact 实际 superseded，新 fact 及收据确实提交；旧 run 按既有领域契约 stale 且 lease 清除，旧 epoch 重入必须在新模型请求前被拒绝。敏感更正 proposal 另测同 epoch 恢复，不用 proposal 冒充真实更正。

## 实际结果

先运行高风险 case_update 单例：

    python -m pytest 'tests/v4/agent/test_tool_effect_recovery_matrix_pg.py::test_effect_committed_before_ack_reclaims_same_epoch_without_second_mutation[case_update]' -q --tb=short

结果：1 failed in 1.68s。崩溃前的实际 case 效果、收据、operation 行以及 started/空 output 均已通过；同 epoch 新 lease 取得后，恢复在 `AgentSnapshotStore._load → reconcile_versions` 拒绝自写版本，抛出 `RevisionConflict("依赖变化不是本轮已证实的写入")`，尚未请求末模型。已交主代理修复；本片不改生产实现、不放宽断言、不设 xfail。

随后独立验证其余分支：

    python -m pytest tests/v4/agent/test_tool_effect_recovery_matrix_pg.py -q --tb=short -k 'not case_update'

结果：8 passed, 1 deselected in 7.37s。通过：memory_write、note_write、profile_update_request、case_add_event、schedule_followup、set_reminder、memory_update 的敏感 proposal 与真实更正 stale 分支。deselected 仅是上面已证失败的 case_update，不能计为通过。

Ruff（E,F,I,B,UP,SIM，行宽 120）及 format 检查通过。未跑本片宽回归；父代理的固定快照全量与此独立，不能合并计数。

## 已知缺口与后续

02:04 时 case_update 是严格失败，随后修复见下面追加记录。现有 completed_step 篡改反例继续保留：将 completed 强改 started、但保留 output/finished_at 的状态不能作为可信自写证据；真实崩溃窗口应是 started 且 output/finished_at/usage 为空，仍必须验证同 run/epoch/seq、原工具输入、真实 mutation 与操作收据。不得遍扫 owner 后把任何变化视作本轮自写。

tarot_start 尚未加入本片，待塔罗文件冻结后补真实运行分支。现有结果不表示来源撤销后的旧 epoch 可恢复，也不表示 P3 或真实供应商已经就绪。

## 07:33 修复与组合复验（北京时间）

`agent_pending_effects.py` 只证明真实尾部未确认 case_update。它从本 epoch 已完成模型的原调用与连续序号、原 RequestLedger 的严格私有快照/请求指纹/来源版本，重建正规化参数；逐一匹配 Journal input_fp、精确 mutation operation/request_key/fingerprint/saved 收据、当前已选择 case 的 revision=expected+1、真实变更字段、原话来源及逐字段 refs。精确 `:case` operation 的 owner/kind/result_id、同事务时间和当前实体更新时间共同约束因果链。core_operations 的 digest 只能核 64 位格式：其原始旧完整 payload 不能从当前实体逆算，没有声称重新计算了该 digest。

Snapshot 在原来源、租约、取消、epoch、人物、撤销与隐私指纹闸门后，仅在同事务更新准确 run dependencies。原冻结字节、真实 started 步骤和原收据均不变；后续仍由 Registry 的实际 mutation 幂等回放再正常 Journal.complete。

并行片将 Journal 确认与 register 放进新短事务，因此夹具改为独立 pool 连接、不取 owner advisory lock、非锁读取 mutation/实体/operation 均可见后再中断。这样证明的是效果实际已提交，不依赖线程本地是否恰有确认事务。并行片另移除写效果到确认之间新增的全依赖 poll；原 Journal.complete/_register 的租约和撤销检查保留。

实际完整窄组：

    python -m pytest tests/v4/agent/test_tool_effect_recovery_matrix_pg.py tests/v4/agent/test_pending_case_effects_pg.py tests/v4/agent/test_loop_cycle_own_revisions_pg.py -q --tb=short

结果：**41 passed in 20.32s**（矩阵 9、新证明 25、原自写/伪造证明 7）。包含真实更正 stale 与原 completed_step 篡改拒绝；取消与旧 epoch 在各自真实入口先拒。新反例覆盖缺/改模型、账本、工具输入、mutation、operation，伪造尾步骤，外部 revision，撤销，当前字段/refs/subject 不匹配。正例单独证明 Snapshot 采纳依赖后步骤仍 started、output/finished_at 为空、usage={}，没有凭空确认或重写冻结字节。

运行中保留的失败：初次接合并行片曾出现 8 failed / 29 passed，包含上述新增 poll 的 6 项交叉回归和 2 项测试入口设置错误；修正入口不改原断言。补同 revision 人物范围反例时，首轮 40 passed / 1 failed 是测试尚未建范围外 subject 的 PG 外键错误；建真实范围外 subject 后，在原范围闸门拒绝并通过完整 41 项。不得把这些在途失败算作先前已绿。

该次组合从已提交基底 `3e732a6b3f0e50347e90a81aac50391aab64250b` 加本片及并行片尚未提交源码执行。关键 Git blob：ToolBatch `a59e6e84472e57a56f9aac3909fd35620858a69e`；pending helper `725bbef0a888526f63e36f1a56a7bf67ffbc472e`；commit_versions `5d679760e1e4c766316cdbcd4ce2050f31fbd6cd`；snapshots `32566cfc6435e9771a09a9c4efc582d5443ea7a5`。最终冻结 blob 随后单独记录；它是工作树组合结果，不能冒称固定提交全量绿。

新增源码、测试及两个最小接点 Ruff/format 通过。没有真实模型、服务器、飞书或宽回归；固定树全量留给主代理在下个允许窗口执行。

07:34 对两个最小接点补充相关窄回归：

    python -m pytest tests/v4/agent/test_agent_snapshots_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py tests/v4/agent/test_journal_recovery_pg.py tests/v4/agent/test_loop_cycle_case_versions_pg.py -q --tb=short

结果：**47 passed in 17.16s**。这与 41 项组合分别执行，不把二者说成固定提交全量。`git diff --check` 通过；新增 helper 269 行、最长函数 40 行；新增测试与支持最多 219 行、最长函数 52 行、单行最多 120。最终冻结时上面四个关键源码 blob 未再变更。8 文件由主代理统一提交，本代理未提交、推送或合并。
