# MOD 旧流式 Outbox 边界储备回执

- 分支 / 最后提交：归属 `v4/mod-organize`；本子任务未执行 Git，由 root 独立提交，PR #10 保持草稿。
- ExecPlan：`docs/v4/execplans/MOD_stream_outbox_boundary_20261021.md`。

## 完成了什么

- 新增 127 项独立验收：合法阶段恢复、原 token/期限、续租后旧 CAS、未知状态全部公开入口拒绝、
  对账七字段隔离、真 bool、明确拒绝的远端 ID、双 freshness、manifest/版本投影严格类型。
- 发现并保留真实失败：已 ack 历史 seq=3 与当前可发送 reserved=2 矛盾，restore 原先未拒绝。
  root 只修改 contracts.py 统一校验历史顺序/界限；本子任务未改产品或独立真值。
- 加入历史逆序/重复反例，以及明确拒绝 seq1 后新操作 seq2 成功的合法空洞正例，避免过严修复。
- 修后新增目标 127 passed/0.29s；两个 P9 兼容套件 1955 passed/25.63s，无排除项。
- 4 个新增 Python 文件 Ruff、format120、AST 类型/大小检查通过；源/测试/样例在兼容测量前后不变。

## 评测分数

09:18:53–09:19:20 北京时间，仅统计 7 个 `stream_outbox_v2` 产品文件：

| 口径 | 已覆盖/总数 | 比例 |
| --- | --- | --- |
| 行 | 492/528 | 93.1818% |
| 分支 | 210/246 | 85.3659% |
| 综合 | 702/774 | 90.6977% |

分支尚未到 90%，如实保留，不能称所有覆盖目标完成。DAY 历史早于官方 legacy 守卫测试，
不能将全部覆盖变化归因于这 127 项。模型实测未运行，真实请求为 0。
覆盖证据：`STREAM_OUTBOX_boundary_coverage_20261021.json`，SHA-256
`d13357cbc8365eb8232b40155bf81f7f2e408ef41dda6fb9d9de7711d96f162f`。
验证证据：`STREAM_OUTBOX_boundary_verification_20261021.json`，SHA-256
`f393cd010ab35680d764b608c1bf81a996fd61304b2791b7eaa9f06602a4222c`。

## 改了哪些关键文件

本子任务仅新增 `tests/v4/p9_v2/coverage_support_acceptance_mod.py` 以及 recovery、capability、freshness
三个 `test_*_coverage_acceptance_mod.py`，另有本计划和证据。
root 修复的产品文件是 `stream_outbox_v2/contracts.py`，修后 SHA-256
`ade48456779b131d3eff32873c12cecac1961ed801f3a8ab05d42c95b1fae624`。
与最小失败证据的 7 源比较，仅此文件变化；原测试/gold 不变。

## 数据库迁移与回滚方式

无迁移或运行态写入。全部为虚构输入、纯状态与 FrozenClock；未连接 PG。
新增测试和证据可独立撤回；产品补丁由 root 审查，不能以回滚来放松 unknown 或来源守卫。

## 偏离设计的地方

无设计偏离。历史记录允许 checkpoint 接入时缺前缀、明确拒绝后留空洞，但已知序号必须严格递增且界限一致。
未知发送仍未知，CAS、双 freshness、租约和 fallback 规则未改。

## 未验证 / 已知风险

分支覆盖不足 90%；逐文件所有未执行行/分支保留在 JSON。codec 二次守卫多受构造校验先行约束，
没有通过绕过构造来刷覆盖。完整合法 core3 freshness 路径仍缺本轮覆盖。
metadata 指纹不等于签名；host freshness 投影不能自证查过当前 PG。主线仍需真实锁行/CAS、
先持久化 dispatched 再传输、当前来源账本、跨进程竞争和平台对账验收。
没有真实模型、网络、飞书、通知、业务或运行态写入；没有读取 Q5 B 或校准 75 条正文；CI 未验证。

## 需要用户或大脑决定的问题

无。本轮真实缺陷已由 root 处理；后续补覆盖不需要改变 unknown 不重发规则。

## 建议后续

独立补可由真实持久化输入到达的恢复形状和 core3 兼容证据；避免为执行内部重复校验伪造不可能状态。
正式接线前，以真实隔离 PG 验证原子持久化与旧 worker 拒绝，保持纯测试与部署证明分开。
