# P9 模块线阶段回执（离线候选模块完成，完整P9阶段未完成）

- 分支 / 代码提交：`v4/mod-organize @ b2924e5f58226751fd44dc764fb6df94b6d31967`；已推送，[草稿PR #10](https://github.com/JerryandShawn/zhiming/pull/10)。
- ExecPlan：[夜间计划](../../execplans/MOD_2026-10-19_overnight.md)。

## 完成了什么

- [x] 按08§9生成七类候选JSON2：回答、提问、记忆回执、提案、跟进、按区晨报、归区标签；全卡最多4按钮/1主操作，回调仅value.t，长正文/依据折叠保留，最终移除status/关闭流式。
- [x] 真实状态显示回执，pending/failed不变成“记下了”；撤销成功由主线明确归一化为undone后显示“已撤销”。提问已选后移除按钮，0选项仍支持自由文字。敏感主动预览不含正文。
- [x] ActionTokenService与内存Store：32字节高熵、仅hash、身份/subject/open_id/kind/目标/指纹/期限全校验、原子once、合法重放不执行、坏actor不消耗、业务operation_id稳定。
- [x] CardKit注入替身：严格递增sequence先预留、300–500ms节流合并、正文覆盖/text_reset、显式关闭、metadata快照/权威final同卡恢复、unknown不重建/不重发、仅uncertain对账、同业务不能换目标绕过。
- [x] close明确拒绝只返回稳定fallback intent，不自行补发；unknown close不生成补发意图。
- [ ] 官方协议核实、真实飞书发送/图片/塔罗/回调/免登、PG持久化/Outbox/租约：均未完成，用户夜间不允许接入。

## 评测分数

200项本模块测试通过0.57秒；四队组合1504项通过3.40秒，含Q1安全补丁后148项、P6 880项、P7 276项。82个新增Python文件Ruff/format120及文件≤400/函数≤60检查通过。卡片构建72项、token58项、CardKit69项、socket/DNS禁止的实际模块组合流程1项。没有真实模型、真实飞书或服务器调用。

已修3个独立发现：in_flight提前对账会重复投递；换目标绕过unknown；无效空final可关闭卡片。参考[Q4_cards_metrics.json](Q4_cards_metrics.json)、[候选JSON示例](Q4_cards_candidates.json)。这些JSON及替身测试不代表官方验收。

## 改了哪些关键文件

新增`channels/cards.py`与contracts/elements、`action_token*`、`cardkit*`、8份测试/替身辅助文件；没有改既有FeishuTransport、gateway、Outbox、依赖或前端文件。

## 数据库迁移与回滚方式

无DB迁移或外部消息，revert本项新增文件即可。MemoryStore仅同实例原子性，snapshot不持久、不认证、不fence旧进程；不能把它当PG权威状态或业务落库证明。

## 偏离设计的地方

按用户夜间指令覆盖P9“先查官方/实发”的要求，只交外部字段标“待对照飞书官方文档核实”的候选。明确close拒绝返回意图留Outbox处理，没有直接发送纯文本；这是为了保留unknown不重发。超4按钮拒绝布局，由主线选操作，不能静默丢撤销/归区。TTL15分钟/最大24小时仅候选配置。

## 未验证 / 已知风险

飞书字段、CardKit限频/ACK、管理员权限/发布/客户端渲染全未核实。callback actor必须由已认证SDK边界提供，kind/entity/当前payload指纹从服务端可信上下文和当前实体重读，不能相信按钮或模型声明。consume成功与业务写的原子事务仍需PG实现；同逻辑动作重复签发仍需按operation_id去重。

旧Outbox仅允许完成run，reconciliation整块覆盖；主线须新建流式意图/租约并合并cardkit命名空间，不能降低来源授权或freshness。权威final、来源撤销、日限、权限/域名allowlist与对账证据都由主线重查。未知不自动补发，卡片可能停在旧正文，需可见的受控恢复流程。

## 需要用户或大脑决定的问题

业务token有效期、管理员权限/SDK与官方字段核实放白天；没有夜间授权请求。真实飞书验证仍需未来逐次授权。

## 建议后续

按接线说明先做PG事务/租约与假传输集成，再核对官方协议和授权stage验证。本夜继续四份接线指南、性能与最终只新增审计，保持草稿，不合并。
