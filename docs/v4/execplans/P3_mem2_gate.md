# P3：v58记忆updated主线闸门

## Scope

2026-10-27人类续作授权按main58，先解除模块线KU01/KU02等待。独立树zhiming-v4-mem2-gate，分支v4/mem2-gate，从无P8基点3b095f397568e783ec05454f855694456bbbca4d建立。不合入未就绪模块、不接P8、不改首发e578，不发迁移或真实模型请求。只41附加段1：updated事件/精确版本闸门、旧事实依赖、公开ids及更新展示；2–5后续再接。

## Progress

- [x] 01:16实际读main58及41附加段1，独立工作树建立。
- [ ] 完成updated精确版本/旧事实闭包及公开回执契约。
- [ ] 定向真实PG、saved回归、迁移逐文件相同检查，提交推送并发布H1 SHA。

## Surprises & Discoveries

slot更新的旧事实保持active但有valid_to/superseded_by，原生proposal变更记录含old_revision/new_revision和两事实ID。旧事实不能仅凭affected_ids信任，应核本轮实际mutation receipt、对应operation和变更记录的精确修订，禁止事后改动被旧前缀冒认。

## Decision Log

updated的主事实与saved一样核整数且相等的revision；旧事实额外凭原生变更记录核验。saved原有策略不放宽。ids是撤销变更标识，不能按模型输入构造，也不引入undo_token迁移。发布前保持原始机器分、历史失败不变。

## Outcomes & Retrospective

实现与验证中；未声称模块KU或完整记忆2.0通过。SSH本wake只读探测结果记录DEV日报；不修改远端。

## 2026-10-27 01:24实际交付

H1实现已完成：updated公开事件和ids契约；loop_codec主事实精确整数revision核验、affected_ids旧事实加入完整来源闭包；_own_revision同时允许saved/updated，历史旧事实额外核本轮持久mutation receipt、原生变更记录精确old/new_revision及三项实际operation（旧fact/新fact/change）。旧前缀不能采用外部新修订；变更记录事后修订也拒绝。saved原路径未放宽。依赖采用仍走owner/subject/case、来源撤销、租约等原闸门。

公开envelope只展示从真实old/new fact重新读取的摘要，呈现“已更新：A → B［撤销］”；原Journal/mutation receipts保持原件，不把展示正文写回计量/操作凭据。static只增转义后的状态文字，没有捏造撤销端点；真正变更ID+revision撤销路由属于附加段2、待模块合入接线，不宣称此时已能点按钮撤销。新增PublicReceipt可选ids/summary与MemoryReceipt.updated同步机器schemas；原未设字段/原saved输出保持兼容。

最终完整定向轮private/safe-narrow-99fd6280f25f46dda0964e9f4fcd4770：106/106，13.82s，metadata/XML/log已根核；覆盖updated修订号布尔/错值拒绝、旧事实闭包、后续外部修改/变更记录修订拒绝、无原生证明拒绝，原saved own-writes/最终提交/连续脚本原有测试。此前6e6bfe258e3a4e0595152d3be56bf2f5为85/85、5.29s；16f2a7e07fed4ca0a97b6d0ccb575f8f为20/20、11.04s（增补精确证明前的原saved回归），均留原件，不拼接声称全量。Node原frontend检查及新增转义/updated状态断言通过，node --check通过。Ruff/check+format120及git diff --check通过。

private/v58_migrations_unchanged.json：8个SQL逐文件canonicalLF与冻结e578原Git字节相同，git diff migrations为空；无P8源码加入本分支，无新迁移/undo_token/M6索引。未跑完整tests/v4、KU01/KU02或CI，不能称模块/记忆候选就绪。真实模型/远端修改0。01:15 SSH探测仍banner timeout/native255，session95538已结束。

Progress以上本轮H1项均完成，推送后在DEV日报第一段写H1闸门已发布+精确SHA，供模块普通merge；不向其他聊天发消息。下一依据模块就绪状态做v58附加段2–5或继续P8，记忆一旦就绪优先合入此无P8分支；首发e578/r46保持冻结。
