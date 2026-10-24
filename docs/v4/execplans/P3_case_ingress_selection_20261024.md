# P3：首次认证入站贯通事项选择

遵循 AGENTS / `.agent/PLANS.md`，北京时间，仅隔离本机PG与Mock HTTP。原完整脚本门与真实请求/服务器/外发门均不变。主线需要修改入站与评测适配，不修改模块线的memory服务、memory_*工具或上下文检索。

## Purpose / Big Picture

历史证明首链暴露真实P3入站缺口：同一实际run已选case，而原source.case_ids为空，两次case_update均AUTH_SCOPE_ERROR。根已核实际诊断XML：08:56:54.778245–08:57:13.063214，原正例唯一复验为1 setup error/17.297秒，未到租约过期或证明。唯一原件在 `private/safe-narrow-7210a07574364b429967d603cf54ec2b/`；首2绿3红仍保留在原历史证明计划，不能当合法自写链。

## Progress

- [x] (2026-10-24 11:35 +08:00) PR18 确切合成 checkout 的 CI 隐私路由顺序回归已做一生产文件两行修复；原失败与受影响事项选择八个目标唯一首链9/9通过，旧测试未改。根与独立代理全文审阅且根独立核三份原件，等待新头实际CI。

- [x] (2026-10-24 08:59 +08:00) 根核ThreadIngress.submit/receive、PrivacyMode.receive/_receive、ThreadService.receive与现MemoryService.receive：选择只传入queue.run，首次存源时遗漏。checked_source的双域检查正确，不放宽它。
- [x] (2026-10-24 09:04 +08:00) 六授权路径静态冻结：新helper43行，新测试167行，Ruff E/F/I/B/UP/SIM、120列格式/AST通过，改动函数最大52行。根全读diff/实际调用方与全部拟测节点，独立二审通过；唯一首链8/8通过、XML2.640秒，09:03:43.060796–09:03:46.613437。根独立核原metadata/XML，证据只见 `private/safe-narrow-589b7809e2604e58928e140628eded99/`；没有重复旧绿、全量或历史证明。
- [x] (2026-10-24 09:09 +08:00) 实际正确入站后，实质改变的共同历史证明夹具5/5通过，两次case_update均真实saved；唯一原件与原失败保留在历史证明计划，不在此重复。旧未成立的2绿不计验收。
- [x] (2026-10-24 09:05 +08:00) 定向证据登记后7c20d40已提交推自身分支；新增CI与正式候选门另核。

## Plan of Work

ThreadIngress.receive新增可选case_ids，submit把原认证options.case_ids传给receive；PrivacyMode.receive/_receive与ThreadService.receive继续传给现MemoryService.receive(case_ids=...)。可新增一个小的thread_case_sources helper，统一规范化/验证不超过8个去重ID、真实owner/subject/撤销，保持现Memory API不改。评测V4Target._request调用相同ThreadService.receive时传实际选择，不手工SQL补授权。

必须在**首次**保存用户原话时绑定已验证选择。禁止在queue补写旧source范围；已有source空scope仍不能靠后续run选case取得事项写权。现Memory.receive允许无版本追加case域，所以新ThreadService路径须在调用它之前核已存在原话的case选择完全相同，不得静默合并授权。旧直接Memory SDK语义不改。

Privacy route input_fp包含规范化非空case选择；空选择保持原持久fp兼容。相同request/source改变选择拒绝且全态不变；无痕带case在原话持久前拒绝，整个隐私选择事务回滚，不产生假成功/残留路由。当前subject、原正文、身份绑定、source_segments与原版本规则保持，不修改工具权限/CaseEffect证明/金标。

## Validation and Acceptance

新增一个真实PG测试文件，最小三组：首次ThreadIngress.submit已选case的source与run范围一致且相同重放不扩权；同事件换选择/跨owner或subject拒绝且全态不变；已有空source经queue不补域且无痕带case不落源。只替代外部传输，不伪造run/Journal/tool receipt。

修完后原历史证明5节点的共同夹具已经实质改变，原2绿未建立合法链，故同5节点须经真实两次saved case_update→quota→原lease自然过期重新验证；必须有真实saved回执、精确revision+2、effect存在断言，不能让删不存在effect的负例凑绿。测试总并行不超过2，根审静态后授权，失败不自动复试。

## Decision Log

2026-10-24 11:33 +08:00：PR18 的 Core run40053670302/job120751726207 已实际失败，checkout 日志确认 59df098d60c38514c24f46acf7a5d80287e8823f（07571eb 合至9f）。v4 为4293 passed/56 skipped/1 failed/2 warnings，2793.49秒；唯一 test_private_case_binding_rolls_back_original_mode_and_run 期待含“长期事项”的 EvidenceError，却被 PrivacyModeService.receive 的无条件 selected_cases 提前抛 ScopeError。原测试保护无痕与长期事项不相容、事务回滚和随后普通请求，必须保留。根与独立代理核 ThreadService.receive 已在实际目的线程确定后执行 selected_cases(private=...)，且 before MemoryService 持久化；本片仅恢复 PrivacyModeService 事务开头的 assert_scope，去除重复且过早的选择验证/import。正常线程的 owner/subject/撤销和原事件选项不扩权仍由既有 ThreadService 验证，不能全局转换 ScopeError（网页403）为 EvidenceError（422），也不放宽 pytest.raises。只改此一生产文件，旧测试全部保留；这是原首次接线的顺序回归修复，不是新产品错误码决策。

2026-10-24 08:59 +08:00：选择贯通放在首次认证入站，拒绝queue事后修域。保持Memory.receive既有实现与checked_source严门；这是真实主线P3接线缺口，不能通过修改新测试种子或补SQL掩盖。改动路径/理由将写当日日报，避免与模块线的记忆2.0工作重叠。

## Surprises & Discoveries

真实provider工具响应与中央ok并不代表工具业务保存：首个历史夹具只有模型HTTP完成，原生工具因source域遗漏而拒写。现Memory.receive还允许不升原话revision的case域合并，因此仅传参数不足以保护幂等选择，必须在它之前拒绝旧事件范围变化；旧Memory SDK保持原行为，由首次入站层保证新的事件契约。

## Outcomes & Retrospective

上述 CI 顺序回归已做最小生产修复，原测试断言完整保留，普通事项授权与重放规则未变。本机唯一首链9/9、pytest2.95秒（JUnit2.941秒），实际开始/结束2026-10-24 11:34:25.086279–11:34:28.918964 +08:00；0失败/error/skip，无警告。唯一原件位于本树 `private/safe-narrow-648f44f3ca8c4ff6b975e9295b856de8/metadata.json` 与同目录完整XML/log，根已独立核。包含原失败、正常首存/同选重放、换选/跨owner/跨subject/撤销四参数、旧空scope不扩权及两种无痕全态回滚；所有是受影响的既有目标，没有新造样本或放宽断言。安全runner清凭据/关追踪/TZ Tokyo、真实隔离PG、实际模型/服务器/外发0。源码Ruff E/F/I/B/UP/SIM、120列format及diff检查通过。

原 CI 的Core旧测试584与前端通过、ModelPort跳过这个失败事实保留。修复本机9/9不代表新头CI已绿或formal/feed可推进，不把上一8/8挪作新代码证明。只改隐私入站的验证顺序，MemoryService、memory_*工具、上下文检索和暂停树未改。

首次认证选择现已真实贯通，8/8验证source/run范围和原segments一致、同选择重放全态不变、换选/跨owner/subject/撤销4例拒绝、旧空source排队后真实工具仍AUTH_SCOPE_ERROR且空privacy fp兼容，以及两类无痕选择10表完整回滚。没有放宽checked_source或现Memory SDK，主线仅复用其首次接收参数；必要路径与理由已写09:01日报，模块线独占记忆服务/工具/检索均未改。

已提交并推7c20d40至自身v4/p3-wire-case-ingress-20261024；首次push因TLS握手失败，仅原样一次重试成功，网络/凭据/SSL校验未修改。后续历史证明片另有真实两次saved及5/5证据，见 `P3_quota_historical_prefix_20261024.md`，不能用本片8绿替代。原完整81门仍69/81、无最终候选或发布Go，真实模型/服务器/外发0，同run恢复/clear/claim/CLI不开放，新CI另核。
