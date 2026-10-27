# P8：准备第二批接线材料

## Purpose / Big Picture
按指令板meta v3及42号第二部分、40号计划交付主线可审阅的接线材料。
Pointer是文档内定位值的路径。材料通过不代表Agent已接线或预测有效。

## Context and Orientation
工作根：C:/Users/Administrator/Documents/Codex/zhiming-v4-p8，分支v4/p8-calc。
复用 charts/p8_adapter.py 的 time_basis、四工具入口；skills/loader.py的SkillLibrary；
charts/tool_evidence.py的pointer及现有三份阿远真实计算样例。
不改变v3默认口径、Agent、授权账本、数据库和web；倒推冻结。无新依赖、无模型请求、无服务器访问。

## Progress
- [x] (2026-10-26 22:49 +08:00) 核对meta v3和干净分支，恢复原续作任务至10-28 22:00。
- [x] (2026-10-26 22:51 +08:00) D1–12契约与主线责任、资料映射和Pointer表，23 passed后推送b94e78b（按Git时刻校正原22:55笔误）。
- [x] (2026-10-26 22:58 +08:00) 四入口与拒绝验证；31/62/92日各3次实测，推送6416672。
- [x] (2026-10-26 22:58 +08:00) 五种白话交界模板、实际柱差异/别名约束，推送c2bc5cb。
- [x] (2026-10-26 22:58 +08:00) 技能32章适用场景、精确体系/topic索引及三份阿远接线用例；定向总计57 passed。
- [x] (2026-10-26 23:24 +08:00) 三份阿远材料；修正候选9a8466ec完整3227 passed/0 skipped；fake80/80、自检48/48；旧Core553通过。
- [x] (2026-10-26 23:27 +08:00) 日报第一段写就绪及验证提交，工具确认续作10-19-08-00-2已PAUSED；不再启动开发，补齐最终交付证据后结束。

## Surprises & Discoveries
原生time_basis归属字段在顶层，不是嵌套scope；四工具才有scope。
原生worker错误会折叠为chart_engine_failure；细错误码不能承诺跨进程保留。
现有合盘入口已在计算前精确拒绝缺失consent；它不替代主线一次性授权账本。

## Decision Log
2026-10-26 23:19：首次完整回归3215 passed/8 failed，均为技能v2.5元数据升级未同步的Schema、五份manifest、绑定表和版本断言。
旧测试保护Schema严格字段白名单、manifest一致和绑定版本；保留全部语义断言，仅同步有意升级的版本常量。
Schema显式声明wiring_applicability严格结构，不开放additionalProperties；不改章节内容、原刊出处或计算结果。
2026-10-26：用42号允许的Pointer逐条映射表和测试，不改动计算口径及历史计算源哈希。
主线负责资料确认、证据登记、授权及可见性；本线仅准备材料与纯规则表达工具。
中档强度、不开子代理，测试任务串行，测试进程至多2；全量仅候选里程碑一次。

## Outcomes & Retrospective
P8接线材料已齐，基于9a8466ec通过本轮3227项完整回归、553旧Core、fake80及自检48。
首次全量发现技能版本升级遗漏，修复严格Schema/manifest/绑定同步后重验；没有放宽白名单或来源校验。
日报已写就绪，续作已由工具暂停。CI排队与Agent实际接线均未验，不能把材料就绪称作产品上线或整个P8 Done。
倒推冻结，旧v3不改。本线无迁移、真实模型、服务器、飞书、合并及子代理。

## Plan of Work
按Progress顺序，每项独立定向验证、提交、普通推送。候选在北京时间15–29分启动完整回归。
每天22时汇总，每两小时记真实进度；40分钟内发布安全检查点。

## Validation and Acceptance
资料缺IANA/clock_basis不能猜测；38条评估仅true可登记r；五种模板只报告实际受影响柱。
对应07场景集的专业解读证据约束；本阶段不执行真实模型验收。
tests/v4完整回归、脚本模式评测和格式检查实际通过后才写就绪。

## Idempotence and Recovery
仅合成资料和只读计算，无迁移。材料可重跑；回滚只回退本次提交，不删除用户数据。

## Artifacts and Notes
接线说明docs/v4/contracts/p8_wiring_for_main.md；证据docs/v4/evidence/P8/。

## Interfaces and Dependencies
复用Core/Charts隔离解释器和既有锁；不新增依赖。Agent工具注册由主线实现。

## 修订记录
2026-10-26 22:49 +08:00 创建，承接暂停前产物，按新材料队列执行。
2026-10-26 22:59 +08:00 记录四个里程碑和57项定向结果，继续候选验证。
2026-10-26 23:27 +08:00 汇总新候选完整通过及自动化暂停，附阶段回执，结束本批材料工作。
