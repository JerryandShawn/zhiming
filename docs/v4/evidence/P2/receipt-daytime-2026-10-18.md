# P2 阶段回执（白天组合合入门）
- 分支 / 最后代码提交：v4/p2-foundation @ 75cbeb7b0d834bbc22550625500bfc7ee5261163；PR：https://github.com/JerryandShawn/zhiming/pull/4
- ExecPlan：docs/v4/execplans/P2_foundation.md

## 完成了什么（对照阶段提示词与14G）
- [x] 从已合并P1基底rebase，保留P1诊断与P2程序时刻；coverage7.11.0/既有锁版本全部保留。
- [x] 重新生成Test七包230哈希并require-hashes安装校验，证据：2026-10-18-combined-validation.md。
- [x] 旧Core553、全部v4 615、原脚本80/80与48自检通过；模型208项/约95%覆盖。
- [x] 28项组合真实PG验证覆盖时刻/诊断同事务、回滚、租约/epoch、repair身份与预算。
- [x] 17/18/19与22/P5b原件独立同步，12文件Git字节与源一致，未越权实现其他线代码。
- [ ] 精确远端候选CI与合并：采用PR当前checks绿门，实际链接/merge SHA由每日汇总补记。
- [ ] P2真实模型质量比较、stage验收：用户最新逐批授权与具体stage授权尚未给出，本轮不执行。

## 评测分数
- 脚本模式80/80、框架48/48；原始报告task/work/daytime/p2-scripted-v1。
- 实测模式：未运行，真实请求0；没有与旧k3基线作跨模型相减。

## 改了哪些关键文件
- consultation.py在原短诊断事务内补权威epoch校验；原provider字段、程序时刻、charge/repair规则保留。
- tests/v4/foundation两个文件补28个组合用例；契约单测仅隔离ROOT fixture。
- requirements-test.lock保留coverage并全哈希；P2原有时间/线程/检索/撤销实现未机械覆盖。
- ExecPlan、组合回归证据与设计同步字节证明。

## 数据库迁移与回滚方式
- 本轮新增迁移0；P2原0005–0007保持原字节，测试合成schema迁到7。
- 仅操作本机可丢弃主线库；未迁移stage/生产。旧P2提交保留恢复ref，未删除共享数据。
- P2前向schema不能直接给旧版本使用；真实恢复另按stage计划授权、备份和撤销账本重放执行。

## 偏离设计的地方（及理由）
- 补epoch诊断拒绝：真实repair测试证明仅lease token不足；新增窄校验保护原批次，不改变repair身份/预算。
- ROOT临时目录隔离使单元测试只测未跟踪源码规则，不削弱真实拒绝P2旧v3基线规则；理由已入Decision Log。
- 新D1/D2覆盖旧自动续跑/模型默认决定，E1不在本轮自行启动。

## 未验证 / 已知风险
- 真实模型质量、k3/k3-256k等价、stage/生产/真实飞书均未验证。
- 上游anyio弃用告警仍在；不影响615项结果，不为本阶段扩范围升级。
- 一万消息snapshot性能证据来自既有P2测试；不把它当整个history API常量内存/延迟承诺。

## 需要用户或大脑决定的问题
- 用户：每次真实探针/E1/E2的明确开始指令；stage/生产均需未来那一次具体授权。
- 大脑：P3/P5b迁移顺序与缓存L5字面验收冲突在P3计划汇总，不阻塞P2合入。

## 建议后续
- 当前候选CI绿后合并P2到v4/main，再从合并基底分别开P3与P1b；前端/命理后续由独立线继续。
