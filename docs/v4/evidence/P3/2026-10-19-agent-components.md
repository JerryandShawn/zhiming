# 循环、快照与提交组件回执（非完整P3）

2026-10-19 07:42 +08:00复核。只有本机隔离PG及ScriptedPort，0真实模型、0服务器、0飞书、0主干合并。

## 已验证

- Loop/Snapshot 59项，15.83秒，0skip：真实工具读写/完整推理签名、跨轮隔离、完成步骤重放、限制/合作式取消、来源闭包、case历史事件后的精确依赖、自己写case继续与冻结前缀不变、外部新修订和新写注册竞态拒绝。代理提供源码hash并冻结，root收录前核对。
- 最终信封/提交组件47项，3.31秒：真实PG原子发布助手消息与core4结果、无效租约/epoch/runtime/无痕拒绝、未知引用移除、引用依赖检查、伪造提问拒绝、真实来源变化与采用来源撤销拒绝；无关写入/撤销不误挡。原core3提交接口仍拒core4，旧行为未整体放宽。
- 事项来源撤销补18项相关回归：goal/title来源清理、独立字段保留、原话quote闭包；已在昨晚验证，最终组合回归另记结果，不将旧结果冒充新全库结果。
- 所有计量仍区分policy units与实际usage；缺可信会员framing时禁止真实发送。

## 使用边界与未完成

没有AgentLoopRuntime.execute装配/API路由；本件只是可组合组件。没有完整M5无痕/插话/2.5秒网关、M7 dispatcher、M8 v4 runner。core4读取helper已写但旧Hermes/delivery/tarot读取端尚未接，不能启用真实v4。

采用来源撤销返回明确RegenerationRequired，第二epoch再次撤销拒绝；实际一次再生成的安全调度尚未实现，绝不恢复已撤销request或正文。自身case更新成功后、Journal完成前崩溃采取失败关闭，未达到所有写窗口透明恢复。连续两个工具在自身修改初始依赖后，ToolService.authority的旧版本接线仍需补完；当前组件用自写后文本结束验证。

case_list结果、tarot draw/reading完整依赖登记仍有缺口；不把工具应用测试视为Loop全血缘验收。U41危机模板、canonical提示词、只读工具并行、配置文件读取、完整评审接线没有交付。模块U4 parser未交，因此绝不宣称相对日期正反各20通过。

无新增迁移，旧0001–0007不改；精确entity版本命名空间保留旧case聚合语义并纳入撤销闭包。默认v3未切换；回滚为停止使用新组件，已存在PG数据不删，正式部署仍需授权B。

目标测试命令：`pytest tests/v4/agent/test_agent_snapshots_pg.py tests/v4/agent/test_loop_cycle_pg.py tests/v4/agent/test_loop_cycle_controls.py tests/v4/agent/test_loop_cycle_case_versions_pg.py tests/v4/agent/test_loop_cycle_own_revisions_pg.py -q`；信封使用`test_envelope_structural.py test_agent_finalization_pg.py`。解释器P2 Core，显式core_test_main回环库、每例唯一schema、凭据清空且追踪关闭。
