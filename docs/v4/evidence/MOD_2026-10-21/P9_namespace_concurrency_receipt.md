# P9 namespace并发接管修复回执

- 分支：v4/mod-organize；PR #10草稿；提交推送号单独记日报。
- ExecPlan：MOD_P9_official_20261021.md、MOD_2026-10-21_continuation.md。

## 完成了什么

- [x] 新增111项独立恢复/当前产物/metadata/旧proof不变量验收。
- [x] 保存8项真实失败：旧prepared/leased、同/不同operation、租约当前/过期都会被错误接受并行候选。
- [x] 仅本轮namespace新增显式迁移门禁；不更改旧状态机、freshness、unknown、fence或184冻结规范。
- [x] 修后53项namespace专项、完整457项与Ruff/format通过；最终性能重新观测。
- [ ] 分支/综合覆盖仍未达90%，实际协议迁移和PG事务/渠道未接线。

## 评测分数

修前8 failed / 0.68s，见P9_namespace_parallel_intent_failure.json；原真值不改。
修后namespace专项53 passed / 0.69s；完整P9专项457 passed / 17.62s（覆盖采样）。
行881/969=90.9185%，分支357/442=80.7692%，综合1238/1411=87.7392%。
来源与新测试hash见P9_official_coverage_boundary_0819.json，原始coverage另存081943文件。
真实模型、服务器、飞书、PG或传输请求均0。

## 改了哪些关键文件

cardkit_official_v3/namespace.py新增prepared/leased拒绝；5个新coverage测试/fixture helper。
接线说明增加legacy_pending_requires_explicit_migration与host迁移责任。
P9_official_state_performance_namespace_final.json绑定修后源码：100完整链中位0.663010秒/76996B，
200崩溃或租约过期路径中位0.778110秒/48050B；1预热、3观测及独立tracemalloc。
计入合成构造/JSON/完整守卫/断言，逻辑400ms不当真实等待；Python峰不等于RSS。

## 数据库迁移与回滚方式

无迁移或已启用通道。旧意图/未知状态和证明保留，不删除、不换key、不绕过对账。
纯merge不撤真实租约；实际迁移必须主线在权威事务中停旧writer并结算/撤租。

## 偏离设计的地方

收紧旧prepared/leased接管，包括同operation及过期lease，避免两套sender同时推进；
这是必要并发修复，不把过期当撤租证明。旧acked/rejected及合法checkpoint证明仍可共存。

## 未验证 / 已知风险

没有PG互斥/进程停用/实际迁移证明。较早83a48c4的CI成功不等于此新补丁CI已绿；
新增测试尚待下一合法窗口完整已完成模块回归。运行中草稿授权、非answer布局与平台未知项仍留主线。

## 需要用户或大脑决定的问题

无本地阻塞，继续独立边界测试。真实迁移/平台验证依原授权边界，不在本线执行。

## 建议后续

主线接线时保持协议所有权与行/namespace双CAS，补真实隔离PG并发测试；
不把单一fence数值相等当成已撤销旧协议执行权。
