# 事项可见范围切换：真实双轮与缓存证明

2026-10-21 07:51，北京时间。仅本机隔离PG15/ScriptedPort；清供应商凭据、关闭追踪，真实模型/飞书/服务器均0。新文件和改动仅主线，前端/命理/模块独占文件不动。

## 原失败与修复

合法case_update将事项改为paused/closed且第一轮成功。第二轮未选择事项，只查询其标题/状态；来源层正确隐藏带case绑定的历史，但人生线程缓存没有可见范围身份，错误将这次合法过滤当作同epoch改写L5，抛context_l5_append_only_violation，尚未到索引最终引用门。原两条完整Runtime断言保留，没有xfail或绕成组件路径。

线程缓存增加visibility_sha256，内容仅为服务端已校验case_ids集合的canonical指纹。ContextEngine预览和RequestLedger实际发送均传同一运行范围；mark_sent在原owner/lease/线程锁事务中重新核验。范围变化、旧缓存缺身份时，沿sources_changed失效分支开启新epoch；同范围的不可解释L5改写仍拒绝。保存不含正文或额外授权，不改ContextEpoch dataclass、冻结Schema、旧已发账本或私密模型快照字节。

## 实测

原两轮与旧epoch/snapshot/Runtime目标先为 **48 passed /11.91s**。随后补视图集合顺序不变、非法范围拒绝、来源版本门不被视图身份替代、真实PG旧缓存缺身份仅重开一次，以及双轮最终epoch+1和未选原文不进入任何新模型请求断言。

    python -m pytest tests/v4/agent/test_context_visibility_pg.py \
      tests/v4/agent/test_case_lifecycle_index_pg.py \
      tests/v4/agent/test_context_epochs.py tests/v4/agent/test_context_epochs_pg.py \
      tests/v4/agent/test_agent_snapshots_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py \
      tests/v4/agent/test_pending_case_effects_pg.py -q --tb=short

最终 **81 passed /22.15s，0skip/0warning**。81包含先前48，不能相加。真实双轮经过AgentRuntime、原case_update/receipt、PG状态、下一run的case_list、Journal和Finalizer，保持未选事项正文与写权隔离。旧同范围任意改写硬拒、来源撤销、过期租约、并发发送仅一方落地、窗口压缩、pending case写入证明等原断言继续通过。

Ruff全规则E/F/I/B/UP/SIM、120列格式与函数/文件尺寸检查通过。首次新增断言出现E501，格式化后重核；没有改产品断言迁就实现。没有修改冻结评测或真实请求配置。

## 边界

本片与独立paused/closed索引状态片共同证明后续只读查询双轮。**本轮case_update关闭/暂停后马上引用原e#仍有另外两条真实失败**，属于selected自写引用证明缺口，由独立片处理，不能借本片81绿称全部事项闭环。完整固定头回归和Linux精确CI仍待验；这不是P3完成、上线或真实模型质量证明。
