# P5b模块：区分类、分区上下文、可撤销整理

## Purpose

用户授权mod板v12、49号模块线最后一项；P7纯模块已就绪ddef556，当前独立树zhiming-v4-mod-p5b、v4/mod-p5b，从本轮再次核实已发布首发9f2506f拉出。只新增organize纯模块与对应测试；不改ContextEngine运行入口、Agent、闸门、路由、调度器，不发任何模型/服务器请求，不自动处理真实历史。完成全部模块后暂停自动任务。

## Progress

- [x] (2026-10-27T09:28:47.635620+08:00) 完整读取18/P5b、22号设计，保留7默认区与人生线程，核对旧模块清单。
- [x] 阅读并挑选复用旧organize模块及测试，先审依赖，不整体合并旧分支、不应用stash。
- [x] 分类/切段/话题聚类/10轮粘性；低置信→日常+needs_review，没本地模型只用关键词并明示。
- [x] 当前区上下文、当前话题最近30轮、其他区7天近况、全局约束置顶/当前区检索×1.5纯投影。
- [x] 审阅先行、仅新增标签、带批次逆操作、改名/合并/拆分/移动/忽略，字段精确apply→undo并保持正文不变。
- [x] 合成600消息30天、分类/ARI/低置信/粘性/性能/撤销验证；真实运行未验证项明列。
- [ ] P5b模块就绪+候选、Draft PR，全部队列完成后暂停。

## Surprises & Discoveries

旧v4/mod-organize已有organize/v2、supplement_v2、export_dry_run_v3及partition_context_v2等纯候选。此前Q5盲B组合门失败已冻结；不得重开B、围绕B调参，旧指标不能当本次证据。只有新合成固定测试及原公开契约用于移植验证。

## Decision Log

优先复用已交付模块，先读代码/调用方与依赖再移植；测试必须在当前首发基点验证。语义分类旧Q5未达标不伪造就绪；如仍失败，在日报第一段写【需要大脑裁定】及最简保守建议：全部低置信进入用户审阅，不自动应用真实数据，独立先完成上下文/撤销模块。新代码保持source/owner/consent/revocation、unknown不重发；context只给纯选择策略，实际ContextEngine接线归主线。只新增标签，绝不改原消息正文。未授权模型下载，未安装ONNX时使用关键词退化而不假称向量质量。

## Outcomes & Retrospective

进行中；本轮P5b只有读设计和建树，尚未运行P5b测试，不计作产品开发结果。P7回执在独立树docs/v4/integration/P7_module_handoff_20261027.md；下一步读旧organize核心及对应公开合成测试。

修订：2026-10-27T09:28:47.635620+08:00，从完整队列进入P5b。

2026-10-27T09:42:14.984679+08:00 已选择原模块root纯引擎/changes/partition，未带v2/Q5盲评或supplement大依赖；只读公开600开发语料、未读/重开Q5 B。首发缺memory.retrieval_types，将无运行副作用的source投影搬入organize/source_projection并改纯模块测试导入；不修改记忆运行文件。旧评测助手搬入tests/v4/organize/evaluate_support，移除默认holdout执行入口，度量/阈值原样保留。新增review_gate绑定精确owner/subject/batch/plan/24h用户批准投影，拒绝覆盖非空旧标签；实际认证仍归主线。

当前定向268 passed（0.88s），Ruff lint/format通过。公开600开发语料：240明确片段233正确=97.0833%，全600消息ARI0.728999，低置信漏审0，模糊120/120待审，完整引擎0.05672s。该公开语料已用于开发，不能作为未见泛化；旧Q5组合门失败保持，不宣称自动应用真实历史获准。新的主线接入建议固定为review_gate及重新验证授权来源。
