# 流式Outbox：恢复已知历史的顺序与界限

本修复仅位于本轮新加的 `stream_outbox_v2/contracts.py`，路径相对启动基底8c554bd仍是新增。
不修改v3运行入口、数据表、序号分配、平台请求或其他工作目录。官方P9新候选及旧unknown/双freshness规则保持。

## 问题与修复

公开生命周期可得到update1已确认、update2已准备，当前预留序号2。若只把持久化历史的已确认序号改成3，
原restore仍可得到能够继续领取的prepared状态；历史与当前序号矛盾却未拒绝。
另一组独立23项先固定真值，旧源10失败/13正例通过，保留真实首失败后再修复。

StreamState构造现在验证每一条**已有**的带序号历史：

- 按历史次序严格递增，且早于当前意图序号。
- 状态为acked的历史序号不得超过last_acked_sequence。
- 无序号的create/send历史仍合法，不把它们当流式序号。

失败以固定中文StreamError拒绝，机器原因为history_sequence_invalid或history_acked_sequence_invalid；不回显正文。
恢复/新建/replace均经过同一构造校验，没有新增持久化字段或迁移。

## 允许的有效状态

主线可以从已有CardCheckpoint开始，早期history为空或只有后缀；检查不要求完整前缀。
明确拒绝过的请求仍占用其预留序号，下一个操作允许跳过这类空洞，不要求连续。
已有原operation的安全重放仍是原有no-op；CAS、token/fence、时限和当前来源的两次核对没有改变。
dispatched恢复仍变uncertain，不因换operation、经过时间或来源重新有效而自动重发。

## 主线接线要求

实际PG必须在行锁/CAS事务核对本次owner/run/business和当前权威账本，保存dispatched后才能调用传输。
metadata指纹只是内容一致性标识，不是签名，也不能证明查过PG。此修复不能发现被恶意host整体伪造的自洽账本。

若恢复拒绝，保留原metadata和已发送状态，进入受控排查/权威对账。不能删账、初始化新意图或换卡作为自动兜底。
unknown只能通过原绑定的可信对账结果结算；校验失败不构成“未发送”证明。

## 本地证据与边界

修前最小1失败以及独立10失败/13通过原记录均保留在MOD_2026-10-21证据目录。
修后127项新增目标通过；两个P9套件兼容1955通过25.63秒，覆盖仅七个stream_outbox_v2产品：
行492/528=93.1818%，分支210/246=85.3659%，综合702/774=90.6977%，单独分支仍未达90%。
独立23项原断言全部通过0.15秒；88→120排版前后AST相同，不删除参数或断言。
这不是全项目/CI/真实PG、跨进程竞争或飞书投递验收，真实请求0。

详见STREAM_OUTBOX_boundary_receipt_20261021.md、STREAM_OUTBOX_boundary_coverage_20261021.json，
以及P9_history_calendar_initial_failure_20261021.json和对应独立修后报告。
