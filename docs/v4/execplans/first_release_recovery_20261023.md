# 核心首发包：增量升级与恢复

首发为P1/P1b/P2/P3，按指令板v8推进；记忆2.0是否随首发须按模块就绪门判断。这里的本机证据不授予服务器访问或发布权限；旧B/D均已取消。遵循`.agent/PLANS.md`，所有时间为北京时间。

## Context and Orientation

复用`tools/deploy_core.py:387`的export_withdrawals和`:405`的apply_withdrawals、仓库mutation_request的持久幂等、TarotService的真实删除与现有LangGraph checkpoint清除。旧b9包及其固定恢复工具/测试保留历史事实，不改hash或重签来掩盖已知非空往返限制。最终候选还未冻结，不填写虚构发布SHA。

## Progress

- [x] (2026-10-23 23:10 +08:00) 最终代码已补owner+draw稳定、无正文的恢复标记；导出去重排序，同一全体owner事务内写入，重复不再增加标记。
- [x] (2026-10-23 23:10 +08:00) 7个新PG行为及3个既有兼容行为均有通过证据（8+1+1定向复测）。真实pg_dump→pg_restore→重放→再导出满足原单调校验，第二次所有表状态不变；跨owner及篡改整批回滚。
- [ ] 冻结最终首发候选，核实增量升级适用迁移、owner/writer、回填与实际解释器。
- [ ] 本机Docker Linux PG15全链、最终候选原生新库恢复、维护门与writer栅栏演练。
- [ ] 编写并复核first_release_stage_runbook.md与first_release_prod_runbook.md；等待用户另行授权。

## Surprises & Discoveries

旧恢复只删除draw，没有留下下一次export可见的原生删除旁账，故原verify_monotone会拒绝STALE_WITHDRAWALS。最终代码新增`tools/deploy_core_withdrawals.py`，保留原export格式及校验，不删除旧断言。已有draw和既有异owner tombstone均阻止换owner重绑定；所有标记冲突导致全体事务回滚。外部checkpoint清除仍是既有提交后边界，须纳入后续Linux全链失败演练。

首链8通过/2失败/1清理错误：新测试的pg_restore缺少显式dbname模式参数；既有兼容节点先缺PG15 PATH，后因安全runner未传USERPROFILE而在Path.home失败。只修新夹具；私有runner为原旧节点补PG15 PATH与指向新临时目录的USERPROFILE，其余凭据清理不变，不修改旧测试、用户环境或公共runner，不提交重复wrapper。

Docker Linux Engine本轮实际可读（29.5.2），此前环境失败记录不能当作当前故障；PG15镜像下载尚在进行，不代表Linux恢复或应用演练成功。

## Decision Log

恢复标记仅含owner、draw_id和固定版本的指纹，以及deleted/deleted_ids/kind回执；不保存牌面/问题/正文，不造原HTTP幂等键。复用已有core_mutation_requests，无新表或迁移。0009保留P5，不改变历史1–8。旧b9继续保留独立反例，当前修复只随最终候选发布；首发开门前可以回退，开门后只按另审止损与前向修复方案。

## Concrete Steps / Plan of Work

相关验证使用清凭据的私有安全runner和本机隔离PG15。代码审阅、定向验证、提交推送之后才进入Linux演练；最终候选增量入口不得复用freeze/install/publish去覆盖既有Core库。Native入口须恢复到全新明确allowlist数据库，验证备份、最新撤销/发送收据、同源解释器、角色权限与重复无变化；旧Native入口仍主动拒绝缺失的生产恢复证明，不能用JSON布尔值解除。

## Validation and Acceptance

场景F01–F04与X03的“不复活、不重复”约束同样适用于恢复。非空备份恢复后实际删除目标、其他owner牌与正文不变、重导出保留所有删除、第二次全表摘要及旁账行均不变；坏指纹/收据/owner须在整体事务内失败。Windows PG证据只解除该代码分支验证项；Linux、正式候选、Web/飞书/报告三个unit、CHART_PYTHON、Hermes wrapper和checkpoint权限仍需各自真实离线演练。

## Idempotence and Recovery

标记key由owner+draw+版本确定，重放返回draw_tombstones_added=0。输入冲突时整个SQL事务回滚；不删除用户数据库或Docker卷，不自动清理失败演练。部署任何异常保持维护门/栅栏并记录，服务器操作须等新授权。

## Artifacts and Notes

私有metadata位于`private/safe-narrow-e24b119d52034f6b964941d0ff2223f3/`（首链）、`private/safe-narrow-d63fc6d3c64b491287fe0c7c2be93f2e/`（真实恢复复测1通过）、`private/safe-narrow-633554d7fb314b37b3d8efe25f0c1a0a/`（原旧节点1通过）。另一次临时wrapper定位错误未执行业务，记录保留在`private/safe-narrow-6d10d0df18d544708bb4fb6ace80978e/`，wrapper已完全移除。并非一次全链全绿；无模型、飞书或服务器调用。

## Interfaces and Dependencies

export保持core3-withdrawals-v2格式，deleted_draws规范化为唯一(owner,draw_id)排序列表。apply新增只读计数draw_tombstones_added；所有旧计数及撤销/收据保护保留。新增helper不引依赖，真实PG15测试用已有本机客户端。

## Outcomes & Retrospective

已修最终代码的非空撤销往返，并完成相关Windows PG15实际备份恢复验证。未完成Docker/Linux整链、生产原生恢复入口或可执行的新发布单，首发保持No-Go；不沿用b9的空样本或旧授权放行。

## 修订记录

- 2026-10-23 23:10 +08:00：记录最终候选删除血缘修复、实际PG定向证据及仍未解除的发布门。
