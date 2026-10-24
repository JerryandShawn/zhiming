# P3 验收缺口审计（只读快照）

记录时间：2026-10-21 01:34 +08:00（北京时间）。核对已提交主树 `v4/p3-agent-runtime@97cd8b27562303e6d66a781d81cf63a494e8c521`，两次读取HEAD相同；审计期间其他代理仍在独立添加set_runtime和旧DOM演练文件，未纳入本片验收。本片只新增本文，不修改代码、既有证据、ExecPlan、评测断言或配置，没有运行测试、模型、飞书或服务器操作。

**结论：P3 形成了真实本机 PG 的运行候选，但尚不能按 AGENTS §12 宣称整阶段完成或可上线。** 原指定脚本最新完整报告是 **46/47**，X03 四条断言仍失败；01:00 固定快照完整 v4 回归为失败，后续只有目标修复证据；旧页面与 v3→v4→v3 的完整 DOM 演练、P1b/P3 组合、真实 K3 encoder 和真实模型质量尚未验收。后续公开决策卡已经接通，不能继续沿用 01:06 计划中“options 尚未接线”的旧状态。

## 1. 审计口径与来源

- 完整阅读 `docs/v4/prompts/P3_Agent循环与工具.md`，特别是实现要求、测试和八条验收标准。
- 完整核对大脑交付目录 `28_夜间作业提示词_2026-10-20.md` 的主线 Z1–Z7、冻结契约及公共规则；文件 SHA256：`be350ed5004ef6874761f2db4928ed7dbc6884a200f8111c495d4c5e52875cfd`。
- 完整阅读同目录 `33_全量开发队列_本周.md`；文件 SHA256：`235b41e021367d9d82aca571114d41459c8d87f399152b1179c4b58bdb668315`。33 号是本周后续队列，不把它列出的 P4–P11 全算成 P3 已完成能力。
- 实现以主树代码为事实，数字只引用已保存的对应证据。本片没有复跑这些命令，重叠目标数不相加。旧证据的“待接线”按后续证据更新，但保留原时间点和失败原件。
- P1b 只读核到独立目录 `zhiming-v4-p1b@6ec4ceeb20fa4e39642461d77e9a0ec105e85d74`。P6 草稿只读核到独立 `zhiming-v4-p3-wire-p6`；不修改、合并任何其他工作树，不向其他聊天发消息。
- 本文不确认 GitHub 此刻状态，不以本机 HEAD 推断远端精确头 CI；P1b 的 CI 更新仅引用该线已经保存的复核记录。

状态含义：**已实现/目标已验**仅指表内边界；**部分/待组合**表示有真实组件但不足以满足整项；**未验/待决**不得在阶段回执勾成完成。

## 2. 原 P3 与 28 号主线逐项对照

| 要求 | 当前实现与精确证据 | 尚缺、不能宣称的内容 |
| --- | --- | --- |
| RuntimePort 后的真实循环 | **已实现/目标已验。** `domain/consultation.py:85` 的 execute 协议由 `application/agent_runtime.py:149` 实现；Snapshot→Loop→Journal/RequestLedger→Finalizer，`RuntimeRouter` 按持久 runtime 分流。`2026-10-21-m6-life-runtime.md`：130 passed/18.65s；`2026-10-21-runtime-api.md`：64 passed/23.47s，另有旧 Core 32 passed+46 subtests/39.78s。 | 这是显式依赖注入候选；默认 from_base 没有安装真实 v4 ModelPort。附件、既有 tarot reading、report、selection、parent_run 等 v4 输入由 `runtime_assembly.validate_agent_input` 前置拒绝，不能写“所有旧模式都迁移完成”。 |
| 循环上限配置与同一回复工具并行 | **部分。** `agent/loop_policy.py:28` 约束标准/深入迭代、时间、工具数、重复、150s/20s 租约。`agent/loop_cycle.py:319` 实际顺序遍历 tool_calls。 | 主树未找到提示词指定的 `config/runtime.yaml`，没有该可信配置加载口；上限目前来自 dataclass 默认/构造注入。同一模型回复内独立只读工具的线程池并行尚未实现。`AgentDispatcher` 的跨 run 线程池不能算这项证据。写工具顺序保持是正确现状。 |
| M2 七工具与 U4 | **七工具已接；U4 按新裁定保留接口。** `2026-10-19-first-tools.md`：136 passed/17.84s，真实 MemoryService/PG/历法/撤销；`domain/time_ranges.py` 为 TimeRangeParser/Unavailable seam。 | 28 Z6 已把统一自然语言解析交模块线。替身返回声明日期不证明相对日期绝对化正确，更不满足原 U4 正反各≥20 的准确度要求；应列为待集成 U4，不反向补第二套解析器。 |
| M3 分层、别名、D2 与 Z1/Z2 | **已实现/目标已验。** Context 层次、依赖与保护约束；估算 `ceil(estimate×factor)+4000`、默认1.15、180k拒绝、actual独立记录/超界告警自调；L5发送预约、同 epoch 已发前缀不改、压缩/有效来源变化换代。`2026-10-21-z1-z2.md`：128 passed/14.77s；R07/万消息2 passed/55.60s。实际每次 primary/critic 请求已由 `agent_model_calls.py:118–129` 接 preview/mark_sent，Loop在 completed 后记原 preflight，用后续 Runtime证据覆盖早期“尚未接Loop”。 | 公开 K3 encoder 未在 Core 环境绑定核验；PinnedK3Counter 是可信 seam，不能拿合成计量或字符/policy_units当 token。R07的18,411与万消息2,626为策略单位；没有真实180k token、缓存命中率或会员 framing 实测。连续3次>60k是持久提醒状态，不自动等于用户已经看见提醒。 |
| M4 计算、修改与工具可见性 | **已实现/目标已验。** ChartsService 被 v3/v4 共用，真实旧引擎适配；chart/memory_update/profile_update_request 入注册，date_calc server-only。`2026-10-21-M4-tools.md`：142 passed/25.27s；Loop相关19 passed/8.87s；真实Finalizer链另1 passed/1.83s。Z3固定顺序、≤15、必需工具预留及危机/无痕优先，`2026-10-21-z3-tool-visibility.md` 最终56 passed/9.27s。 | 原生P8未合入，真太阳/交界诊断/新推运等不可称已完成；chart_skill仅有可见性槽位，没有当前实际注册实现。date_calc默认不披露待裁定，不可写“模型可调用全部第二批工具”。无痕临时排盘仍拒绝。 |
| 塔罗 U7 与 case | **部分/目标已验。** 固定draw、24h防反复、明确坚持才重抽、真实读取/恢复；TA01–03在原47完整报告通过。`2026-10-21-case-index-lineage.md`：26 passed/8.00s，case_list仅索引读，不把读ID变成写授权。 | case closed/done/archived 的最终引用、Tarot native draw/reading 全血缘仍有后续切片；case索引不是用户事实，不能填 used_fact_ids。TA脚本通过不证明所有专业牌面引用都有完整血缘。 |
| M5 人生/无痕与 Z4 | **已实现/目标已验。** ThreadService、自动无痕路由、24h生命周期、私密快照/消息/清理；只确认一次的脱离线程提醒。`2026-10-21-private-runtime-z4.md`：96 passed/25.85s；`2026-10-21-runtime-privacy-bridge.md`：24 passed/8.06s；`2026-10-21-privacy-maintenance-hook.md`：15 passed/5.22s。 | 自然退出清路由并按24h保留，API显式close立即清正文，这两个行为有区别。旧 `/api/chat` 不接受客户端 thread_id/incognito/runtime 提示，显式新线程走 thread API；这是对原P3可选参数描述的受控入口偏离，应记入最终回执，不能称旧参数直接可用。未做真实浏览器隐私体验验收。 |
| M5 运行中 inbox | **已实现/目标已验。** 持久 inbox_wait、真实模型请求快照/Journal证明采用、终轮cutoff、失败/未采用fallback重新排队；旧token不能ack新lease。`2026-10-21-m5-ingress.md` 最终35 passed/18.68s；`2026-10-21-m5-loop-sources.md`；`2026-10-21-merged-regeneration.md`20 passed/9.17s。 | 多来源恢复最多64条初始源；私密和其他复杂撤销输入保守拒绝自动重生。不能写“任意输入/任意来源规模都可恢复”。 |
| M5 飞书2500ms合并/X07 | **已实现/目标已验。** Gateway只持久收件/合并/queue，不直接consult；保留多条native原话，重启重放只一run，一份最终outbox。M5最终35项；M8独立扩展X07真实PG+ScriptedRuntime+传输替身，只发送一次到替身。 | 无真实SDK接入/飞书送达；2500ms为受信固定窗口，poll延时不等于精确2500ms响应。M8 13项扩展成绩独立，不加入原47分母。 |
| M6 提交/自写/撤销后一次重生 | **已实现/目标已验。** Finalizer核真实lease/epoch/source/state、真实自写operation/receipt；`2026-10-21-M8-runtime-regressions.md`连续自写1 passed/1.63s，`2026-10-21-merged-regeneration.md`20 passed/9.17s。当前原问题撤销不重生，辅助撤销有受证原始来源指纹才重建一次。 | 全部工具种类、每种可写步骤的每个崩溃点尚无完整逐项覆盖矩阵；单memory_write X03恢复不等于所有写工具均完成kill-after-k验收。复杂输入限制仍在。 |
| M6 critic一次修订与正式提示词 | **已实现/目标已验。** `agent_review.py:92` 独立材料/真实PG评审proof；`LoopCycle.revise`只一次、text-only；普通错误skipped仍需提交闸门。正式06与增补H的版本/hash见 `agent/prompts/manifest.json`，system1.1.0；M6 130项目标及options139项目标覆盖。 | 这是当前受信旧critic协议，不等于33号P6校验2.0/校准/第15项一致性检查已经集成。没有真实主/评审模型质量或人工校准；record_only不能解锁真实改稿。 |
| M6 公开 options/ask/final | **已实现/目标已验。** 01:11切片从同run/epoch成功completed工具步骤取最后成功卡，逐字段校验引用/保存回执；真实提交后公开、SSE缺事件幂等补齐，critic审实际卡并绑定hash，revise抑制原卡。`2026-10-21-present-options.md`：新16 passed/7.53s，相关139 passed/29.38s。 | 旧D01仅观察真实工具步骤，不单独证明公开卡链；以这份新证据为准。旧工具unknowns无输入，输出空列表，自由text可逆性保守unknown；没有前端卡片DOM/真实飞书卡片证据。 |
| U41 危机程序兜底 | **已实现/目标已验。** 15正+15反程序规则，config/crisis固定模板校验；模型不可用/额度/拦截/20s无正文及输入计量失败路径；整批有效入站来源与运行中危机补充均识别。`2026-10-21-U41-admission-fallback.md`7 passed/3.68s；`2026-10-21-u41-turn-sources.md`13 passed/6.52s；扩展S01–03实际Runtime验证。 | 取消/来源撤销仍阻止发布；兜底不放松租约。blocked为类型化故障替身，不证明供应商物理分类。规则不是完整危机分类器；没有真实S类100%质量结果，不能用程序模板通过替代实测门。 |
| M7 两通道/串行/通知/续租 | **已实现/目标已验。** `dispatcher*.py` 与 PG claim共同栅栏，interactive2/background1、总3、同owner/thread串行；事务提交才NOTIFY，取消需PG标记，2s轮询fallback，20s续150s。`2026-10-21-m7-dispatcher.md`最终30 passed/8.94s，含真实跨连接通知和lease移交。 | web安装由后续Runtime API证据覆盖，不沿用M7初版“尚未装”作现状。所有worker仍须容量一致；本机结果不是生产负载/公平性上界，后台报告实际来源尚未接通。 |
| M7 真实本机HTTP取消≤2s | **已实现/目标已验。** `test_dispatcher_http.py:101` 启动真实loopback静默SSE，首段落库后cancel→PG cancelled，interrupted只一条，0最终投递；M7实测47ms。M8原47 01:00整轮X04实测32ms，先前定向15ms各自保留。 | 这些是不同运行，不能择优或求和；不是外部模型/服务器延迟证明。thread HTTP TestClient cancel只验证持久标记/不提前清lease，不能单拿它冒称网络取消时延。 |

## 3. core3/core4 读取端逐个清单

共用边界 `application/read_result.py:15` 先 validated_result，再严格 EnvelopeV1 投影；core4 `text→answer`，core3保留answer并提供text。未知schema、假validation与越权不能靠字段名猜成成功。

| 原要求/扩展读取端 | 代码定位与实际覆盖 | 缺口边界 |
| --- | --- | --- |
| Hermes validated_payload | `adapters/channels/hermes.py:150` 调共用helper，core4仍核真实run/依赖。 | 本机兼容，不是Hermes服务器wrapper发布。 |
| delivery _fresh | `adapters/delivery.py:46` 取持久run、validated_payload和run.dependencies，原Outbox指纹/不重发保护。 | 无真实外发。 |
| tarot finish_reading | 真正实现位于 `adapters/tarot.py:288`，内部调用validated_payload；提示词旧路径 `application/tarot.py:297` 已漂移。 | 只接受对应成功run/全等结果，不表示所有v4旧reading输入已开放。 |
| `/api/chat/{id}`、`/api/runs/{id}` | `adapters/web.py:466–474` 投影answer/result；owner与鉴权反例、同一正文回查。 | HTTP投影不是旧浏览器完整DOM验收。 |
| `/api/history` | `memory/history.py:97/137` 已存回复/缺失回复回退共享helper，撤销不复活。 | 主历史排除私密，不拿跨线程聚合替代ThreadService.history。 |
| `/api/feishu_history` | web端读取实际ScriptedRuntime提交run/回复，不提高assistant来源权。 | 无真实飞书查询/显示验证。 |
| report manifest | `adapters/channels/reports.py:74–94` 保留schema_version/guidance/真实依赖，准备delivery前分离已知report元数据。 | **读得懂core4，不代表能用v4生成报告**，见下一节。 |
| 历史回填 | `memory/backfill.py`已从真实core4 used_*与core3 cited_*分别核验，私密不转life，sent/uncertain不改。`2026-10-21-core4-backfill.md`38 passed/22.99s。 | 早期M6记录的“通用backfill只认core3”已由后续切片补齐；没有对真实历史执行回填，缺血缘的旧记录明确skip。 |

共同读取证据：[2026-10-21-M6-readers.md](2026-10-21-M6-readers.md)，最终26 passed+2 subtests/10.73s，先前含旧渠道/历史/Web63 passed/30.28s；计数重叠。未发现以上列明的reader仍仅接受core3，但未穷举未来新增API或外部消费者。

## 4. M8 原47、旧DOM、开关与回归门

| 验收门 | 精确证据/状态 | 放行前仍需什么 |
| --- | --- | --- |
| 原指定脚本100% | **未完成：46/47，97.8723%。** `m8-v4-2026-10-21/full-0100/2026-10-21-scripted-v4-scripted-v4.{json,md}`；79个合成步骤/18.833s；source SHA256 `3a4be6a7304871a5bdc84191c8125686a03555996cc8108a2d689d37dda59c14`；scoring corpus `aebc92157a4d3cebc7f2408757413e8e92e634006b6ad7e51ed828717cdb17f6`。 | X03仍四失败：`turn[1].db[2]`、`turn[2].db[2]`、`turn[2].db[3]`、`turn[2].events`。真实SystemExit→过期lease→同epoch重领→事实/助手各一已验；网页memory_write后尚无校验发送意图却要求queued/sent Outbox，与P7边界冲突，须大脑裁定。不能造Outbox、改旧断言、剔除X03或把status=complete写成全过。 |
| T/R/Q及安全扩展 | **独立13/13。** `extensions-0100/`，27合成步骤/4.761s；扩展corpus `d0e932d174a38ea1406c7cbd903eda1384f08cdff236fb691e517450def48978`。 | 不增加原47通过数，不改变v2.1基线；脚本模型不是真实质量。 |
| 实测T/R/Q≥80%、S100%、基线对比 | **未验且当前禁止无人值守真实请求。** v4 live target明确拒绝；全部上述供应商请求0。 | 待人工在线“开始”批次、P1b中央门及可信encoder就绪后另行执行获准范围；不能由夜间自动任务创建授权。 |
| 旧前端DOM完整显示v4答复 | **待实测。** `static/app.js:485–489` 仍按data里的type/result消费旧流；v4 `web.py:181` 改送冻结命名事件，旧循环不会直接消费新final/text_delta。但 `sendChat:494→recoverTurn:436→GET/api/chat/{id}`已有完整结果回查，可在流结束后显示投影正文。 | 静态差异不足以判必然失败，也不足以证明成功。需真实原旧JS+DOM+本机HTTP/PG显示正文/收据，含回查路径与错误恢复。root已分配独立DOM演练，本审计不改static/**，不提前记通过。新前端线Mock截图不能替代该门。 |
| v3→v4→v3开关/原行为 | **部分。** owner settings.runtime默认v3，新operation固定runtime、重放不随开关换版、缺Agent/meter不回退；Runtime API旧Core目标已有证据。 | 固定HEAD尚未包含 `mingjing_core/tools/set_runtime.py`；收尾时独立代理已添加在途文件，尚无本片可引用的最终验收，本文不碰。仍需真实受信CLI+三轮全链路证明，尤其切回后core3、新旧run身份、其他owner不变与在途处理。不能把测试fixture直接改settings算管理员工具验收。 |
| 固定完整回归/CI | **未达当前头全绿证据。** 00:00固定103431a/远端064954e为1288 passed/284.68s，但不含后续M5/M7/M8。01:00固定76c62b8/远端5c10f53：42 failed/1484 passed/407.34s；Core581项/700.501s有1失败。 | PG工具PATH修正后同快照restore模块3 tests/1.748s OK；后续隐私62/57、组件138等目标修复不能改写旧全量失败。需新冻结tree完整回归及对应精确头CI；本文没有查远端，也不把目标数拼成全量绿。 |
| stage计划与阶段回执 | **计划已有、No-Go。** `docs/v4/release/P3_stage_plan.md`含主owner切换、drain/cancel、切回v3、core4兼容与回滚。 | 计划01:06的options状态已过时，管理命令/DOM正在续做；需在验收收口时更新living docs。B1条件B/D只含固定b9，不含P3；本审计不是正式P3整阶段回执或部署许可。 |

## 5. P1b、day/week与本周集成边界

| 边界 | 当前事实与证据 | 不可提前宣称 |
| --- | --- | --- |
| P1b中央HTTP守卫 | 独立P1b树具有 `models/quota_http.py`、quota_legacy、QuotaGuard、退役入口拒绝、可信角色、全停、U39与体积策略。第四切片 `2026-10-21-v3-wire-slice.md`：1030 passed+19 subtests/101.24s。主P3当前没有quota_guard.py。 | **P1b与P3尚未实际集成。** P3 RequestLedger是上下文发送计量/epoch门，不是中央账号额度门；主树models.yaml主模型仍是k3/model_env及旧thinking预算，不能写“P3已全面锁k3-256k/U38/U39”。 |
| 人工开始入口 | 独立P1b `tools/member_start.py`：真实stdin TTY输入精确“开始 E1 第 N 批”，1–10场景、15分钟PG授权、安全收据；无yes/confirm开关，管道不接受，不自动下一批。收据加载仍逐POST核中央PG。见legacy-manual、manual-scope-d2两证据。 | 主P3未包含该CLI，不能以P1b测试通过推断AgentDispatcher primary/critic/后台请求都已穿中央门。自动化不能代用户在TTY输入。 |
| k3-256k等价脚本 | 独立P1b `tools/probe_k3_equivalence.py`默认mock，固定场景/两模型、物理尝试≤20、出错即停；`2026-10-21-equivalence-mock.md`8 passed/0.22s，20 Mock请求/0真实。 | 只证明离线协议演练，不是模型盲质量等价/256k容量或真实能力验证。 |
| P1b精确CI | P1b保存证据 `2026-10-21-frozen-legacy-integrity.md`01:31更新：修复本机4ec0d97/远端03230c6、tree2918b79，run39462173453/job118764176145 success；冻结102项/11源hash保留。 | 这是另一候选的合成CI记录，不是当前P3或未来集成merge CI。本片不再查外部状态，后续文档head需单列身份。 |
| day/week及定期报告 | 现有报告支持daily/weekly/monthly/quarterly，上海日程与旧worker仍在；`CoreReportAdapter.prepare`以 `mode=scheduled_report`、selection请求服务，`CoreReportWorker.main`走from_base。新core4 reader能读其结果。 | v4 route只允许mode=chat且拒selection，故切owner到v4后，当前报告生成入口**会安全拒绝而非自动变成v4报告**。background通道容量测试不证明报告任务已接入。33号P7晨报/报告编排、P8 daily_transit/window_search等须集成，不能把旧日报/周报仍存在写成新编排已完成。 |
| P6草稿/模块线 | P6结构+legacy_lint接线只在 `v4/p3-wire-p6-20261021` 独立checkout，默认关闭可信注入；有真实模块来源manifest和PG目标，普通lint告警、提交闸门不放松。模块纯逻辑及契约是来源，不等同主线接入。 | 未合主P3；P6v2 critic、人工校准、P8一致性检查、U4、记忆2.0、P5b区/话题、SSE核心仍是33号后续集成队列。不能把wire目标通过归到当前P3整阶段通过。 |
| 集成分支/迁移/上线 | 当前本地分支清单未见v4/integration；`merge_roadmap.md`是计划。0008归P1b、0009给P5bB，按Z5合入编号；P3自身无新迁移。B1固定b9只1–7，不含本候选。 | 没有完成33号“P1b→P3→模块→P8→P10→文档”的实际组合或Core/v4/Charts/web逐步回归，不合v4/main/main，不以集成授权代部署。Linux/服务器/B1证据另轨。 |

## 6. 建议优先的三个剩余技术项

1. **收口可执行的P3验收链。** 完成正在独立推进的受信set_runtime与原旧JS三轮DOM演练；修复后新固定tree跑完整Core/v4，并在新头复跑原47和扩展13。X03先保留原失败并取得大脑契约裁定，获批后独立版本化新增断言，不用工程假发送换绿色。验收产物应包括三轮run/runtime/schema、DOM截图/断言、回执和真实本机取消时延；当前不代做已分配任务。
2. **在v4/integration实际组合P1b与P3。** 明确主/评审/后台的可信构造、call_scope与中央guard，实际逐HTTP测试两槽/角色分区/额度全停/取消释放/人工收据，以及计量缺失零POST。主P3旧k3/thinking配置、P1b新U39 wire、0008与P3同run恢复须作为冲突点逐个验。可信K3 encoder仍缺时保持真实发送关闭，离线组合可以先完成。
3. **补齐循环内核两个明确实现差额。** 受信加载config/runtime.yaml并保持LoopPolicy不可抬高硬限；同一模型回复中独立只读工具有界并行、写工具顺序、日志顺序/重放/取消/副作用一致。补可写工具崩溃点矩阵，以真实PG证明“所有工具无重复副作用”，避免只靠memory_write样例宣称完整。配置/并行不接受模型或HTTP参数开启，跨run Dispatcher仍保持原栅栏。

报告生成v4接线、完整P6/P7/P8/P9/P10、模块SSE24h清理等依33号在集成分支继续；不是本审计新实现。真实模型质量、真实飞书权限/发布和服务器部署都必须使用对应明确授权，离线证据不代替它们。

## 7. 本片交付与限制

仅新增本文件；无数据库迁移或运行配置修改，无需数据回滚。既有计划中列出的历史状态没有在本片覆盖，本文给出新的交叉审计快照供主代理收口。未运行任何测试或外部请求；没有更改其他线文件、评测基线或冻结Schema。本文冻结后由主代理统一提交推送，最终阶段回执仍按AGENTS §11另交。
