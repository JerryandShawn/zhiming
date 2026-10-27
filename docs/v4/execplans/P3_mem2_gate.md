# P3：v58记忆updated主线闸门

## Scope

2026-10-27人类续作授权按main58，先解除模块线KU01/KU02等待。独立树zhiming-v4-mem2-gate，分支v4/mem2-gate，从无P8基点3b095f397568e783ec05454f855694456bbbca4d建立。H1已精确发布416605312775597c2ba86607821aca7cc08f2053；本轮按58允许的独立附加段4，增加画像投影后的结构化资料保护。不合入未就绪模块、不接P8、不改首发e578，不发迁移/真实模型请求；原生服务尚未存在的2–3、5保留待实际合入。

## Progress

- [x] 01:16实际读main58及41附加段1，独立工作树建立。
- [x] 完成updated精确版本/旧事实闭包及公开回执契约，01:24交付见下。
- [x] 定向真实PG、saved回归、迁移逐文件相同检查，提交推送并发布H1 SHA。
- [x] 05:00完成独立L2 field保护接口及实际构建调用，42项定向通过。
- [ ] 模块就绪后合入，复核真实profile_items组合路径，接实际服务路由/调度/R35及46完整门。

## Surprises & Discoveries

slot更新的旧事实保持active但有valid_to/superseded_by，原生proposal变更记录含old_revision/new_revision和两事实ID。旧事实不能仅凭affected_ids信任，应核本轮实际mutation receipt、对应operation和变更记录的精确修订，禁止事后改动被旧前缀冒认。

## Decision Log

updated的主事实与saved一样核整数且相等的revision；旧事实额外凭原生变更记录核验。saved原有策略不放宽。ids是撤销变更标识，不能按模型输入构造，也不引入undo_token迁移。发布前保持原始机器分、历史失败不变。

## Outcomes & Retrospective

H1及独立L2保护已实现并定向验证；模块尚未就绪，真实画像服务组合/路由/调度/R35与46完整门仍待。SSH只读探测结果记录DEV日报；不修改远端。

## 2026-10-27 01:24实际交付

H1实现已完成：updated公开事件和ids契约；loop_codec主事实精确整数revision核验、affected_ids旧事实加入完整来源闭包；_own_revision同时允许saved/updated，历史旧事实额外核本轮持久mutation receipt、原生变更记录精确old/new_revision及三项实际operation（旧fact/新fact/change）。旧前缀不能采用外部新修订；变更记录事后修订也拒绝。saved原路径未放宽。依赖采用仍走owner/subject/case、来源撤销、租约等原闸门。

公开envelope只展示从真实old/new fact重新读取的摘要，呈现“已更新：A → B［撤销］”；原Journal/mutation receipts保持原件，不把展示正文写回计量/操作凭据。static只增转义后的状态文字，没有捏造撤销端点；真正变更ID+revision撤销路由属于附加段2、待模块合入接线，不宣称此时已能点按钮撤销。新增PublicReceipt可选ids/summary与MemoryReceipt.updated同步机器schemas；原未设字段/原saved输出保持兼容。

最终完整定向轮private/safe-narrow-99fd6280f25f46dda0964e9f4fcd4770：106/106，13.82s，metadata/XML/log已根核；覆盖updated修订号布尔/错值拒绝、旧事实闭包、后续外部修改/变更记录修订拒绝、无原生证明拒绝，原saved own-writes/最终提交/连续脚本原有测试。此前6e6bfe258e3a4e0595152d3be56bf2f5为85/85、5.29s；16f2a7e07fed4ca0a97b6d0ccb575f8f为20/20、11.04s（增补精确证明前的原saved回归），均留原件，不拼接声称全量。Node原frontend检查及新增转义/updated状态断言通过，node --check通过。Ruff/check+format120及git diff --check通过。

private/v58_migrations_unchanged.json：8个SQL逐文件canonicalLF与冻结e578原Git字节相同，git diff migrations为空；无P8源码加入本分支，无新迁移/undo_token/M6索引。未跑完整tests/v4、KU01/KU02或CI，不能称模块/记忆候选就绪。真实模型/远端修改0。01:15 SSH探测仍banner timeout/native255，session95538已结束。

Progress以上本轮H1项均完成，推送后在DEV日报第一段写H1闸门已发布+精确SHA，供模块普通merge；不向其他聊天发消息。下一依据模块就绪状态做v58附加段2–5或继续P8，记忆一旦就绪优先合入此无P8分支；首发e578/r46保持冻结。


## 2026-10-27 05:00 独立附加段4：结构化资料与时辰提示保护

main58仍允许2–5并行先做。先核附加段2后发现当前无P8主线还没有memory2_slots_undo等原生模块服务；撤销依赖只存在未就绪模块树。没有提前合入/复制模块、没有写501占位端点或假服务，按同板切到能独立验证的附加段4。模块最新首段03cc0bb指定37/37+4/4过，但仍未记忆2.0就绪，9ef7262完整失败原件不改。

新增context_fact_guards.fact_item复用原始L2事实JSON格式，未知时辰提示条件/正文/alias/排序不变；build_layers在fact_layer画像投影之后调用preserve_field_facts，只从当前已授权SourceSnapshot.facts恢复有field的资料。已有结构化事实项按原位置重建，缺项追加且required=true，普通画像可代表的非field事实不重复添加；来源版本仍沿原injected_versions闭包。画像声称准确不能覆盖原生time_unknown/precision unknown，撤销或其他owner事实不能凭画像ID被恢复。fact_layer只是复用同一render helper，正常输出保持逐项相等，既有context cache/epoch前缀稳定性测试保留。

private/safe-narrow-66c5a397b8144dbeba5bf9cc097bd9d4实际42/42、12.69s，原metadata/XML/log根核exit0/fail0/error0，无skip/warning。含真实PG资料、存储画像的纯投影输入、unknown/False/exact/gender五边界、已被画像改写的资料恢复、撤销和跨owner不补回、实际ContextEngine调用及原fact/message版本闭包、原上下文/历史窗口/epoch兼容。Ruff/check/format120三文件与diff--check过；没有额外全量/真实模型/CI请求。

验证限度：当前主线没有模块的profile_items加载器，测试明确没有提前导入该服务；已确认画像作为真实PG存储行进入纯L2投影边界进行策略验证，不能据此声称记忆2.0整条画像产品路径已通过。模块就绪正式合入后，必须保留build_layers这个后置保护，并用真实profile_items组合再验。未新增migration/undo_token/M6索引，不覆盖H1原发布报告或其旧8 SQL相同证据；本轮只改agent上下文和测试/本计划，不需要刷迁移/treehash。

04:55一次SSH true仍banner timeout/native255，session39035已结束，无认证/远端命令/修改。原PG55480/PID50516只核存活未启停，无后台测试。batch2 P8头9ba30488、首发e578/r46未改，本树保持不含P8。下一模块一就绪立刻在此树普通merge后接附加段2–3/5与46门；若仍未就绪，切回P8缺资料确认等独立余项，不反复尝试不存在的模块API或重跑H1/本轮绿测。
