# 晨报公开边界加固接线补充（2026-10-21）

本补充对应北京10:10:18结束的有限兼容观测。公开入口、输入输出类型和零外部效果约束不变；
原接线说明仍见[晨报编排器](DAY_briefing_20261021.md)。本轮没有新增订阅、发送、保存或数据库入口。

## 调用方需要知道的变化

`calendar_snapshot`与`CalendarSnapshot`遇未知时区给固定`BriefingError`，异常不带用户提供的key。
P2节气快照除了日期、布尔和枚举校验，还要求
`days_to_next == (next_at.astimezone(owner_zone).date() - snapshot.day).days`。
准备和实际投递之间的15分钟保守限制不变：06:45准备的P2快照应在07:00发送前重新生成，
不要把本轮输入一致性校验当成放宽该限制。

P8渲染器在需要对象的十神、关系及西占证据路径上显式检查JSON对象形状。
坏规则不会因标量的`.get`抛未捕获异常；仍按已有路径省略该坏规则，其他有效规则和历法继续可用。
紫微证据中的合法星名标量保持原契约。完整doc/claim/alias/hash检查、正午瞬间说明和不跨周期外推均保持。

新增内部`current_manifest.validate_current_batch`由`compose_briefing`调用：
交付授权通过之后、任何正文生成之前，同一批同`source_id`的当前投影必须在
scope、revision、value hash、active、revoked、incognito字段上完全一致。
冲突给固定`brief_current_source_manifest_inconsistent`错误，不选第一份或最后一份。

参与集合包括所有typed item当前来源状态（含撤回/停用状态）、实际使用的订阅typed状态，
以及结构/alias和doc/scope/revision/hash都匹配的P8当前投影。不会先过滤撤回的一方来消除冲突。
坏、缺失或不匹配的单份P8继续省略，global关闭/停订继续提前阻止交付。

## 主线责任与回退

上述检查只证明纯输入彼此一致。来源状态和profile revision必须由可信host从权威存储读取，
并在实际发送事务内重新检查；typed对象、P8 parse、短alias或SHA均不能自行认证来源当前有效。
本模块仍不访问PG、模型、网络、通知或平台接口，不自动投递。

遇整批当前投影冲突，主线应停止这次晨报组装并重新取当前权威快照；不能挑一个局部有效状态重试发送。
P8单份省略可继续历法/安全内容既有回退。没有数据库迁移或数据回滚；若撤回本补丁，由root按提交回退，
会同时撤回本轮边界保护，旧首次失败证据应保留以便复核。

## 验证与限制

原30项独立预期和断言未改：首轮25过/5失败，root审读授权后30过；晨报、day_pipeline、reports三套
471/471通过。9产品行597/640、分支215/254，综合90.82774%。新helper明确计入分母。
这不是全项目回归或计算质量证明，也没有重新测性能；旧晨报性能报告仍只属于其旧源码。

证据：

- [冻结矩阵](../../evidence/MOD_2026-10-21/BRIEF_public_boundaries_frozen_matrix_20261021.json)，pre/frozen/post SHA均为`1f77c413625f6f24c059cd9c7fd372c388b613459fb032632dd2bd1719cdaf9e`。
- [首次失败](../../evidence/MOD_2026-10-21/BRIEF_public_boundaries_first_target_20261021.json)、[原30修后](../../evidence/MOD_2026-10-21/BRIEF_public_boundaries_fixed_target_20261021.json)。
- [有限兼容与材料快照](../../evidence/MOD_2026-10-21/BRIEF_public_boundaries_compat_coverage_20261021.json)，308材料集合/字节before/after一致。
- [9文件覆盖原始JSON](../../evidence/MOD_2026-10-21/BRIEF_public_boundaries_coverage_final_20261021.json)，SHA`ae60ab7caaa723a4f76667f5bdb3cd5a75b14049d8801eec39e73b28cd0402f8`。

9源聚合SHA为`b81054bd97d3eeb0f410a0b928a563eafa34d06b109409ebc3a5c183eb10a666`，
算法是对兼容报告`product_source_sha256`映射按key排序、UTF-8、无空格canonical JSON再SHA256。
该快照绑定本次观测，不表示未来HEAD永久同源。

待决：`context.target_layers`为含`daily`子串的字符串而非列表时，P8自由context契约没有明确产品口径；
本轮未新增此假设或测试，不阻塞已确认的边界修复。
