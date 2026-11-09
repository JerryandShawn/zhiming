# P5 所选项撤销与运行中失效 · WIP

2026-10-24 02:41 +08:00。在本机隔离 PG 的真实 v4 Runtime 上执行 F01、F03、F04：F04 1/1 通过，F01/F03 0/2，原评分契约不变。当前累计分批证据 31/37 通过，M08/KU01/KU02/F01/F03 五项失败，F02 一项未执行，未就绪。

F04 在第一次真实模型端口调用时，先验证目标事实已进入持久化冻结上下文，再实际撤销。旧批次不能提交；由既有 AgentRegenerator 自行生成 epoch 1、regenerations=1，最终上下文不再含撤销事实，最终仅一条回答。没有修改 Agent 循环或闸门，也没有写入预期计数。首轮评测驱动用 raw queue_run，真实请求证明守卫拒绝；改用实际 ThreadIngress 后通过，未改写指纹迁就守卫。

F01/F03 的初始各层并非空夹具：F01 有 1 个真实 embedding、1 个 profile_doc 视图、2 个 scoped FTS 命中；F03 有 1 个 embedding、2 个 scoped FTS 命中、真实运行的 4 条非空事件及 1 个非空步骤输出。删除后上述层全部为 0。模型不能给出 DB/receipt/event；初始派生实体通过真实本机 native stores 创建，向量仅 [0,1] 合成索引，不声明检索质量。

失败照实保留：F01 的 native deleted 与原 retired/cancelled 断言不符；F03 保留空审计 tombstone，而且来源 fixture 标签与 native id 不同，原五个实体列表断言失败。没有把 deleted 改写成 retired/cancelled，没有隐藏 tombstone 来刷分。此处需要主线/大脑统一逻辑视图和 native 存储契约。

新增 MemoryWithdrawalService 提供绑定选中 ID 的当前用户动作：严格复核 owner/人物/事项、版本、原话时间、当前明确命令、持久化权限。消息和 operation_id 双重绑定，旧按钮不能删另一个目标。删除来源连同事实更新链及现有隐私级联，触发原 on_revoke；下游失败会回滚整个事务。回执只留 ID/状态，来源已忘记后不能重新还原正文。

相关最终组合 21 passed；补严格布尔授权守卫后新增受影响检查 3 passed；语料/旧哈希/M01 补证 6 passed，前一动作组合 7 passed（有重叠，不相加）。无重复全量。公开证据仅聚合；完整合成报告留 ignored private。真实模型、飞书、服务器请求均为零。
