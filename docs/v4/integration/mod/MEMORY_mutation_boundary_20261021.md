# 记忆变更边界接线小补

本轮 24 项公开输入验收及 583 项 memory2 兼容通过，未改变产品接口或原行为。
计划指纹用于核对内容，不能作为用户授权；主线仍需同 owner/subject 的当前来源、版本、epoch、
真实 Clock 和事务 CAS，不能让模型 JSON 直接构造已授权的 MutationPlan/Confirmation。

元数据计划只能归档/退役现有事实，不得创建、删除或改 event_end 等内容。保存操作的结果已删除或
不在权威当前投影时，旧保存重放返回 unavailable；已经成功遗忘的操作即使 tombstone 不在当前投影，
仍可幂等返回 forgotten，但不会重建 tombstone 或正文。这不证明本模块执行了 PG 物理删除。

两个非阻塞口径留待主线/大脑裁定：metadata after.revision 应由谁保证单调、write_status/summary 应由
哪个可信层确定。本轮没有新加这两项政策或断言，不能把接口当前接受范围当作设计已确认；这些字段
不能直接采用模型或客户端的“已保存”自报。真正提交成功的权威 receipt 才能对用户称已保存。

四文件覆盖及未执行分支见本轮新 JSON；它不是 PG 并发、action token、前端回执或部署验收。
