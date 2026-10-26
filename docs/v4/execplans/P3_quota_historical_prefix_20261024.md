# P3：quota 原运行 completed 前缀的历史版本证明

本活计划遵循 AGENTS 与 `.agent/PLANS.md`，仅隔离本机 PG / MockTransport，使用北京时间；不清中央停机、不领租约、不执行原运行，不开放 attached send 或 CLI。候选全脚本门仍关闭。

## Purpose / Big Picture

下一片同 run 续作必须从 Journal seq1 验真重放。真实 CoreObservation 的 completed 模型会严格核原 RequestLedger.versions；若本轮随后合法 case_update 已推进版本，原历史模型会先于工具重放被拒。不能为此篡改冻结请求、用当前版本覆盖历史，或放宽正常发送 authority。本片先提供只读原生证明，尚不将证明接入任何执行权限。

## Progress

- [x] (2026-10-24 08:42 +08:00) 根核实际 StepAttempts/LoopCycle/原版本链 API；二审确认历史请求先核版本、后回放工具。已有离线自写测试未覆盖 core 观察链，不扩写为已验真。
- [x] 新增只读 native helper（282行/最大函数43）与独立 PG 测试（最终289行/最大52），Ruff E/F/I/B/UP/SIM、120列格式/AST通过；不改既有生产校验、记忆、工具、黄金场景或公共资格接口。
- [x] 根已逐行审两文件与实际复用调用方，独立二审通过；仅授单槽三个必要风险组（1+2+2共5节点）。失败保留现场，不重复稳定性测试。
- [x] (2026-10-24 08:55 +08:00) 首链真实08:52:48.228756–08:54:14.254755，2通过/3失败、85.069秒。所有夹具触达真实3次Mock请求/中央quota与lease自然过期，但合法两次case_update没有被证明：正例先在case revision+2失败；historical_revision在seq3版本前置失败；missing_effect删后没有断言原effect存在，helper未拒。故不接受“2绿”作原合法自写链验收，原证据保留 `private/safe-narrow-f1be15d17c3c45208994e96b972b9a51/`。根仅批唯一正例红节点的有界真实tool拒写码与source/run case范围诊断，未改helper/生产或自动重跑另外4。
- [x] (2026-10-24 09:09 +08:00) 首次入站选择已独立以7c20d40修复；共同夹具改用正确真实入站并断言seq2/4两条saved回执、精确revision+2与真实effect存在，负例实际DELETE RETURNING一条effect。因原两个绿未建立合法链，根审后对实质改变的共同夹具重验全部5节点：5/5通过、无错误/跳过，91.051秒，09:07:03.122774–09:08:35.140481。根独立核metadata、全部XML与有界诊断属性，原件只在 `private/safe-narrow-f345125b987f46c498cc966503d5918b/`；不与原失败、入站8节点或完整脚本混计。
- [x] (2026-10-24 09:13 +08:00) 已提交推ddbdc8c至自身v4/p3-wire-quota-history-20261024；首次push无法连接GitHub443，原样一次重试成功，网络/凭据/SSL未改。完整CI、真实续作与真实模型仍另闸。

## Plan of Work

当前分支 `v4/p3-wire-quota-history-20261024`，原实现起点 f048dd0，现从已推7c20d40的真实首次入站选择修复继续；两片前置证据不混计。新证据接口为 `completed_model_history(真实RequestLedger, owner, run_id, epoch, model_seq)`，只接受原生非offline ledger与repo，并拒已有外层事务；独立 READ COMMITTED / READ ONLY 中两遍完整读并核摘要，不能把事务旧snapshot自相等当持续权限。来源范围限人生线程原始 ingress，原scope/epoch/runtime/status/cancel/deadline与撤销仍核；当前已adopted inbox保守拒绝。Journal最多256步，输出仅身份/摘要与 execution_authority=False；不会把新证据接入任何发送或恢复权限。

新增 `mingjing_core/application/agent_model_history_evidence.py`，从真实 owner/run/epoch/model seq 读取当前 run、completed Journal、原 agent_model_request、原冻结上下文和本轮 case effect 链。输入标识不授执行权。返回只含身份/摘要的只读 evidence；不得接受布尔开关、伪快照或 caller 自报版本来免检查。保存前后关键 PG 行需重新核对，任何漂移拒绝。

只接纳真实 completed model；请求 schema/hash/subject/input_fp/role/name 与实际行一致，原 assistant output/usage 按现有编码验真。所有原实体依赖须仍属原 subject、active、未撤销。非 case 依赖严格原版本。case 版本差异仅允许原 epoch 正规 case_update 的完整连续链：对照原 `assert_case_effect_chain` 的全部断言，复用其纯读 intent / effect attestation 组成，覆盖正规模型意图、原 mutation receipt、before/after、operation digest 与原事务时间，终点等于当前真实实体。历史 model seq 的版本必须等于初始 revision 加该 model 之前实际 completed case_update 数；不得直接采用最后 revision 或接受将来写入倒灌。缺环、同正文外部修订、跨 owner、撤销均拒。

返回 evidence 不包含可调用 permit，不连接 StepAttempts.authority/verify_completed，不修改原 request、Journal、case、中央 usage 或额度。将来只有活、不可序列化、原 quota/新 lease 绑定的 resume permit 才可消费这份证明；正常 begin/prepare/before_send/finished 的发送版本检查继续严格。

## Validation and Acceptance

新增 `tests/v4/agent/test_eval_quota_history_evidence_pg.py`，通过真实 Agent runtime / CoreObservation / MockTransport 完成 case_update 后触发实际 quota。不得把离线合成 Journal、手写假的完成行、伪中央 UUID 或 monkeypatch 证明函数当成功路径。必要行为三组：真实历史模型 seq 在合法自写后只读证明成功且所有 PG/HTTP 状态不变；外部同正文新修订/撤销拒绝；破坏自有测试 effect 链或历史版本对应关系拒绝（破坏只作反例）。同 helper 对未来步骤、跨身份及原 request 漂移拒绝可并入原组，不追逐矩阵数量。

新 helper/测试各目标 ≤400 行，函数 ≤60 行。静态 Ruff/格式/尺寸由代理完成；根完整审阅后再授测试槽。当前五个 CI 红的修复验证优先，主线测试总并行不超过两个。

## Decision Log

2026-10-24 08:48 +08:00：继续实际调用方核对发现 `_source` 经 current_source_ids/ThreadInbox 仍会进 _leased/FOR UPDATE；reconcile_versions 的 pending_case_receipts 也会 FOR UPDATE，均不作纯读调用。只复用纯读 `_initial/_original_call/_check_intent/verify_effect` 等组成，来源另以真实 original ingress_sources/source_segments、source_policy、精确quote与撤销区间核验。当前已adopted inbox原话保守拒绝，明确列未覆盖，不把缺少 lease-free adoption API 当空列表或猜授权。原链全部断言仍需对照，任何差异只可收紧而不能省掉。

2026-10-24 08:45 +08:00：原 `load_completed_intent` 通过 Journal._leased 并 SELECT FOR UPDATE，不能直接用于已过期租约的只读资格。新 helper 只允许复用其确实纯读的组成重建原生 CaseEffectIntent并覆盖全部原链断言；不 monkeypatch 租约、不改旧authority。成功组需真实持原token renew为1秒、实际等待自然过期，证明只读证据不依赖活租约。任何会写入或FOR UPDATE的高层快照接口均不可调用；成功返回仍无执行权。

2026-10-24 08:42 +08:00：先抽取无写入、无执行权的历史证明。中央 exact-clear / 原 lease reclaim / pending-step 一次性 permit / 完成结果与二次 quota checkpoint 仍属于后续真实恢复协调器，不通过本片自动打开。当前已推 e2af97d 的 pre-clear witness 保持原接口和权限语义。

## Outcomes & Retrospective

静态实现、根逐行审阅与独立二审完成；修复独立真实入站缺口并加强共同夹具后，5/5首次建立真实两次saved case_update→quota→原租约自然过期的只读历史证明。seq1/3成功、未来未完成步骤/跨owner/既有外层事务拒绝；同正文外部修订、实际撤销、缺失effect与错置历史revision均拒绝；12表完整状态与HTTP数不变，写入/清停/claim/发送陷阱未触发。原2绿3红及单节点诊断失败均保留，不能改写成首次全绿。

本片只验收历史证据，不替代原physical UUID证明、pre-clear witness、中央 exact-clear、lease/attempt执行permit；旧全部发送路径与CLI仍硬关。限制为人生非无痕线程、正规原始ingress且无当前已adopted inbox、running/未cancel/未过原deadline、最多256steps；超出范围保守拒绝。没有真实同run恢复、全量脚本或新增CI绿的结论，真实模型/服务器/外发0。

## Surprises & Discoveries

旧intent/source/reconcile高层校验均可能领用原lease或锁行，不能因名称像“读取”就用于过期恢复资格；只能复用经调用链确认的纯读组成。首次真实core夹具另发现业务source范围未贯通，故原2个拒绝绿不能代表建立了合法自写链。该入站缺口已独立以7c20d40及自身8节点验证，历史证明须另行检验真实saved回执/effect，失败证据保留，不能拼成一次绿。
