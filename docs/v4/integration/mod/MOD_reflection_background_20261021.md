# 记忆后台反思与“关于我”接线说明

入口包为 `mingjing_core.application.reflection_v3`，只新增文件，复用冻结 `memory2` 与 U4。它输出纯调度意图、待主线复核的工作候选和八节画像视图；不创建 run、不真正入队、不调用模型、不写入/归档/删除事实、不改画像、不主动联系。全部 `ReflectionEffects` 固定为零，候选不是 saved 回执。

## 主线必须提供的当前输入

`MemorySnapshot` 包含已认证 owner/subject 的当前事实、来源、snapshot revision 与 source epoch。源正文和事实必须由权威查询取得，不能接受模型或客户端自报。代码重新检查 scope、原话连续区间、source revision、当前 active/revoked/incognito/optout、原话敏感策略、said_at/recorded_at 与事实有效期；source epoch 变化会使旧意图失效。

`ThreadState(scope,id,revision,last_activity_at,source_ids,...)` 的 source_ids 是主线核对过线程归属的完整集合。`MemorySource` 本身没有 thread_id，纯模块不能认证“这条源确实属于此线程”；主线须在查询事务中保证关联。`processed_sources` 是 `ProcessedSource(id,revision,content_sha256)` 集合，摘要绑定源正文、原始时刻、role 与 origin；`processed_epoch` 记录上次完成处理的来源代际。

当前粗粒度 MemorySource flags 不能替代数据库的区间撤销账本。主线投影前必须查询原话 anchor 对应的撤销区间；无法证明区间仍授权时，应保守标记 source revoked 或剔除相关事实/条目。数据类型和内容 hash 都不是权限证明，也不是自然语言正确性验证。

`BackgroundPermit(scope,revision,current_revision,enabled=False,quota_stopped=True,active=True)` 是主线明确后台配置与 U38/额度状态的纯投影。缺失返回结构化 blocked；这不是新增用户确认流程，不要求用户在线回答。配置过期、disabled、quota stopped 或失效均停止。实际运行仍须主线在权威事务内再次检查额度、取消、线程锁和持久租约。

## M1：候选入队意图

`schedule_reflection(*,snapshot,thread,scope,clock,permit=None,operations=(),timezone="Asia/Shanghai") -> ScheduleDecision` 返回 `enqueue/noop/blocked` 和可选 `ReflectionIntent`。kind 固定 reflection，lane 固定 background。

idle 按 UTC 经过时间至少 600 秒触发；03:00 兜底按注入的 owner timezone 计算，支持当天03点后的补偿检查，与 idle 独立。近期有对话但没有正在运行的线程，也可能因03点兜底获得候选；真正并发准入仍由主线处理。`daily_completed_on` 抑制同日兜底，成功完成后主线原子保存当天日期、cursor 与处理 epoch。主机 Tokyo 时区不参与决策。

若当地03点不存在或重复，目前返回 `daily_wall_time_needs_host_policy`，整次不转为别的触发；未擅定 DST 早/晚或平移策略。这是保守限制，主线可在明确策略后扩展适配，不能当作已完成真实定时器。

无痕、incognito thread ID、temporary、不活跃线程、正在运行或未过期租约、时钟早于已观察活动等都不能入队。现有 queued/running ledger 也阻止同线程再入意图。相同 operation 重放必须同时匹配 thread_id 和输入 fingerprint；不跨线程误认重放。

意图绑定 scope/thread、原始最后活动时间、thread revision、当前完整 source ID 集合、processed cursor、snapshot revision、source epoch、permit revision、trigger、not_before 和 timezone。host 才负责 queue CAS 与 `pg_advisory_xact_lock`，两个并发纯函数调用得到相同意图不代表实际只入队一次。

## M2：复核工作候选

`plan_reflection_work(intent,*,snapshot,thread,scope,clock,permit,profile=None,current_profile_revision=None,settings=None,confirmations=(),extracted_candidates=(),existing_gaps=()) -> ReflectionWorkPlan` 在工作前重新检查当前来源、内容摘要、role、原始时刻、epoch、thread 活动和后台许可。跨03点不会单凭当前 trigger 改变而否定此前合法 idle 意图；新活动或来源变化仍会停止旧意图。

当前接口在 thread.running 或活跃租约下保守停止，没有实现“当前 worker 持有自己的线程租约”证明。主线可先在受保护的准备事务中生成候选，真实反思 worker 的所有权适配仍是后续接线，不要伪造 running=False 绕过已有锁。

当 epoch 已变化且所有授权 manifest 为空，只输出 `InvalidationCandidate` 元数据，交主线重算/失效派生资料；不生成 summary、新事实、画像提案、日期修复、归档或跟进候选，不复活旧内容。

工作结果包括以下候选，均尚未执行：

| 字段 | 实际能力与限制 |
| --- | --- |
| episodes / rolling_summary | 按原始源时序、六小时间隔分组的逐字片段；每片段最多480字符，有 source/revision/anchor。method 为 extractive_quotes_only，mood/conclusion 为 not_inferred，不是 LLM 情景叙述或情绪判断。助手片段保留 assistant 角色。 |
| fact_candidates | 仅显式注入的遗漏事实候选；必须来自当前线程原话，复用 Q2 原话与敏感策略。未配置抽取器时明确 llm_missing_fact_extraction_not_run，不返回假模型结果。save 是原策略分类，不是保存成功；仍需主线 Q2 plan_write/apply 和回执。 |
| duplicates / gaps | 当前已授权事实的严格归一去重，以及冻结 Q2 的0.70局部否定/反义规则。相同普通注入事实只记 omission，可能否定冲突只生成 gap，不输出自动事实。无槽位城市更正等未命中规则时不能声称已识别语义冲突。 |
| date_repairs | 复用 `memory2.event_time_extended_v2.absolute_event_candidate_extended`，用原始 quote 与 said_at 解析，保留原文；有歧义只形成日期缺口。不修改原事实，不使用画像生日猜日期。 |
| profile_proposals | 复用旧 reflection_candidates 的 source/fact-bound 提案。缺当前画像快照不补造目标；pinned 和手改项只列 protected，不能被后台覆盖。旧 ChartSummary.trusted 不进入第7节授权。 |
| archive_candidates | 仅依据明确 valid_to/event_end 的到期元数据候选；未删除、未归档。 |
| followup_candidates | 未来具体事件的原始时间和来源版本；未选择发送时刻、未发送、未创建通知。实际后续需接 P7 的事件后时机、quiet、日限、K2迟到与幂等账本。 |
| gap_priorities | 仅依据 host 显式 mentions/blocking 的规则建议，1–5，最多返回15条。超额给 host review warning，不自动删除、关闭或提问；已有 asked/dismissed 状态不能当新问题重启。 |

敏感源正文不进入自动抽取式摘要；已保存敏感事实也要显式当前分类授权或绑定 confirmation 才可进入画像派生。拒记、secret、无痕优先，出生资料仍走专用确认流程。assistant_claim、note 和命理解释不晋升用户事实。

## M3：八节“关于我”

`ProfileEntry(scope,item:memory2.reflection.ProfileItem,revision,anchors=(),origin="user_fact",active=True)` 为旧 ProfileItem 加上归属、版本和当前原话锚点。`ProfileDocument(scope,revision,snapshot_revision,source_epoch,entries=(),active=True)` 是可信 host 的当前画像投影。entry 的 fact/source 集合及 anchors 必须与当前可用事实完全一致。

`render_about_me(document,*,snapshot,scope,clock,current_profile_revision=None,settings=None,confirmations=()) -> AboutMeView` 总是给出固定八节；缺当前文档版本、snapshot revision 或 epoch 不一致时返回八节空视图和 warning。外 scope 直接固定中文错误，不泄露条目 ID/正文。pinned/手改不豁免来源撤回；来源失效后过滤，并保留省略 metadata。

`origin="user_fact"` 显示“依据用户事实的条目”，原话另行显示；`analysis` 明确显示“推测（不是用户原话）”。正文归纳和 origin 分类必须由可信 host 审核，anchor/type/hash 只证明来源绑定，不能证明文字必然由原话蕴含；用户手改也不自动成为真值，不新增用户审批流程。第7节目前固定未验证，尚无权威 P8 历史档案/claim 映射接线。

typed view 保留原始 text 和当前 anchors；Markdown 转义 HTML 和控制字符，避免将原话当标签、链接或标题执行。网页仍须使用原有 DOMPurify/安全 Markdown 管线，不把本转义函数当浏览器安全沙箱。来源撤销后主线须先确定性失效派生项并重新查询页面，不能一直展示旧缓存。

## 接线位置、恢复与未完成项

主线应在后台 dispatcher 的 reflection kind 分支取得最新 host 投影，先调用 schedule，再以稳定 operation_id 原子登记队列；实际执行前重查 permit、源、epoch 与租约。对话 interactive 通道继续优先，不能等待该纯计算候选。

新实体保存仍走 `application/memory.py` / 主线记忆2.0服务的真实写入、确认、撤销和失效传播；画像编辑/读取接未来 `/api/profile-doc`，不能直接持久化本模块返回对象。真正 LLM reflection prompt、工具循环、情绪/结论提取、跨区近况摘要、真实线程滚动摘要写入、用户下次打开时“补记N条”的回执便签均未执行。没有实际 saved 回执时不能声称已经补记。

没有迁移或删除入口。回退是不导入新模块，原 worker/画像路径保留。D4使用提醒继续关闭，没有紧急联系人、使用时长提醒或推送行为。

## 本地证据与性能口径

自有97项与独立143项合计240通过，包含1000自有FrozenClock随机及独立500随机、03点/跨午夜/DST、源全文/role/时间/epoch变化、单槽双当前、敏感、注入去重/冲突、pinned/手改撤源、空manifest仅失效、八节与字面渲染。独立矩阵和工具是脚本/合成契约证据，不是模型沉思或人物推断质量评测。

`tools/mod_week/benchmark_reflection_v3.py` 的两个路径分别是每样本100次完整 M1→M2→八节画像，以及1000次撤源epoch→纯失效候选。计时包括 fixture JSON 解析、14条来源及事实/画像投影构造、来源和敏感/当前性复查、真实纯函数路径与输出断言；只排除导入、fixture字节读取、source hashing 与报告文件写入。一次预热、五个 wall-time 样本、单独 tracemalloc，证据写 `docs/v4/evidence/MOD_2026-10-21/DAY_reflection_performance.json`。没有数据库、模型、真实定时器、队列或通知延迟；Python分配峰值不是进程RSS。

该证据实际生成于08:26:03+08；100次完整路径中位0.6199911秒、Python分配峰369,493字节，1000次失效路径中位0.3992524秒、峰44,335字节。记录源hash且工作期间无产品漂移。

三个可重生成的合成输出摘要由 `tools/mod_week/reflection_samples_v3.py` 产生，最终证据 `DAY_reflection_synthetic_samples_final.json` 实际08:29:03+08。普通完整场景得到2个抽取式片段、1个重复候选、1个缺口、1个日期修复、2个画像提案、1个归档和1个跟进候选，均未执行；用户编辑场景保留2个protected目标；撤源场景只有1个失效候选且画像8节全空。此前无final后缀的样例证据保留为工具格式化前快照，不作为最终工具hash；两份均没有私人正文。
