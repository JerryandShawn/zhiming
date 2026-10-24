# P1b：加固 Kimi Code 错误、协议、额度与调用入口（离线首切片，阶段未完成）

本 ExecPlan 遵循 `.agent/PLANS.md`，四个活文档段落随实际证据更新。正式分支`v4/p1b-k3-hardening`于2026-10-18 17:34 +08:00从P1/P2均已合并的`v4/main@b9a89b6f84f7bebb640de080548010859aae630c`创建。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b`。已实现U37离线首切片与禁关思考配置闸门；完整阶段未完成，真实请求0。

## Purpose / Big Picture

让会员调用具备一致的错误动作、可追踪的真实 POST 计数、跨进程在途限制，以及完整工具循环推理回传。模型、评审、后台、评测和探针共享入口；错误或风控不能靠换同一会员的模型绕过。默认 v3 路由与旧业务预算保留。真实请求只在用户在本聊天明确启动相应批次或探针后执行。

额度账本是只记录时间、模型、状态与用量的持久表；在途槽位是一次HTTP请求期间占有的跨进程许可；工具循环是模型请求工具、收到结果后继续回答的同一运行。它们不改变来源授权、固定塔罗、owner隔离或送达不明不重发契约。

## Context and Orientation

设计来源：原 P1 提示词、17 号研究 §6、`docs/v4/prompts/supplements/P1b_增补_K3会员端点加固.md` 与同目录 `00_索引.md` §4a。正式基底及P2合并号为`b9a89b6f84f7bebb640de080548010859aae630c`；P2候选1444a49的CI 39114527541所有步骤成功后才合并。P1 已于 2026-10-18 合入 `v4/main@7b45a781921e6fa2e875319a12af433f0cf505b4`；P2已合并，原P1、P2阶段分支保留。

复用 `models/port.py` 的规范消息与 tool_cycle、`models/transport.py` 的 HTTP/SSE、`models/provider_diagnostics.py` 的受限公开诊断、`models/metering.py` 的物理 POST 前计数，以及 Registry 的角色解析。P2 已有迁移校验/权限授权；迁移 0008 为本阶段预留。

文件归属：主线修改已有 models/config/runner/probe 与迁移和接线；独立模块线拥有新增 `models/quota_guard.py` 核心及其单测，主线消费真实实现、审查接口、做集成，不另写假守卫抢占。P3 的上下文压缩、危机兜底、工具循环与上下文 token 守卫属于 P3；不改 web/**、P10、P8、charts/skills/knowledge。

## Progress

2026-10-24 19:43 +08:00：已读v26/R23并核M01原件。core30于19:36:37停止，6完成：T05/T08/T14通过，T09/T10/TM01失败；M01 incomplete/score=null，余23未运行，安全6题未执行，不能写安全0/6失败或最终3/30。core物理25（批10/10/5，实际中央batch尾号1/2/3），加接入累计13，窗口38；key已清。M01 attempt=http-be585aed31144eebab26c86ef15c8564，中央status=unavailable/latency11938ms；原report stop_reason=provider_http_error、HTTP码空。usage表无HTTP/type/message列，StepAttempts只存result_kind和terminalhash，关闭追踪且私有日志无原HTTP错误；不能事后恢复状态码或消息，不能断言5xx/超时/400/403或额度。按v26第3条判断不了则提醒，本轮真实请求0/不重发，不改原report或把未知改unavailable来续跑；前6结果和原k31_results汇总保留。唯一安全摘要docs/v4/eval/k31-r22_try2-afab37d3b8884b73af671417ecd76e33.json已补原报告hash、诊断缺口与三物理批，无正文/密钥。v25其余首发真实题runner仅default/core30且core批准绑定CORE30集合，所需余题/日期/P3去重suite需改代码，按板“需要改代码，跳过”；当前core尚未完整结束亦不抢跑。v24 stage/prod单仍待绑定/生产缺口，未称stage就绪。


2026-10-24 19:32 +08:00：已执行v23/R22；新增有限unavailable题头重跑支持，17/17定向，唯一索引新代码树P1b计划19:22。冻结/pushed f87fc97a9a3329782ca702577ec3e268b66c7bc5，同源R11 19:25:46–19:28:59通过48/48、日期7/7、69/69、X02、离线core30 30/30，sourcece8cd8aabe4f143d8ad7f69453553ba375b7ced076b92cbbfe36c1a118056b8e，四原报告已核，原81及延期不改。距19:14:50失败已超10min，第二次接入重跑4请求通过，接入累计13/20（旧失败/浪费均保留），工具2轮/调用1次/额外0，K31/high/推理及1591字完整长答、factor1.15。control=probe_k31_afab37d3b8884b73af671417ecd76e33；通过后已立即启动core30，实际中央首批v7-a7b47c996ada43a28162e94539e8e645-1已有7物理请求/inflight0快照，非最终总数，不把接入13当总窗口请求。核心仍在途/未有最终accepted；supervisor private/r22_retry_pending.json及子private/k31_r22_try2_eval_pending.json为唯一路径，core如unavailable固定10/30min最多2次，只未完成题新run，其他平台停止不重试。等待/在途不重复启动、不改冻结源码，无SSH/服务器/飞书/外发。


2026-10-24 19:16 +08:00：已执行v22/R21，代码候选44889a319de4af870dec77ed7577c8d6091bf4ba已推且冻结，生命周期/主外评/额度恢复旧白名单与三处core-k31 token一致性已修，旧c21基线不动。必要旧45通过、新完整3/3与追加token1/1，原夹具计量失败保留，唯一证据索引代码树P1b计划19:11。新同源R11 19:11:28–19:14:42 complete/exit0（48/48、日期7/7、69/69、X02等价、离线core30 30/30），source8793e582058e39e2da728781168ad8e9fd8d9d6360d8403d29c3d55f4e40f902，四原报告已核，原81仍71/81与12延期不改。随即重做接入，control=probe_k31_492a7468964e4c718ba9e1c4d1168ec3；19:14:50停止：首请求unavailable、无有效响应记录，真实新增1、累计9/20，中央batch=v7-e4bdfd24fc2748898602cec69ab1661e-1/K31-TOOLS/status unavailable，inflight0、stop/reset空，不能称403/额度恢复时间或核响应身份成功。未生成新候选complete接入证明，不能拿旧e708证明批准新448。core30尚未启动/0请求/无core原报告或rollup，不记0/30失败；keyfinally清。未自动重试/换control或账本。唯一安全摘要docs/v4/eval/k31-r21-492a7468964e4c718ba9e1c4d1168ec3.json。


2026-10-24 18:53 +08:00：已执行v21/R20。新冻结候选e708e684109ce50e06c8c172cbcd959d5ee53f2c，同源R11于18:46:50–18:49:49通过48/48、日期7/7、69/69、X02等价、离线core30 30/30；source0f30288760dc7935c22113b2f9c36df66cab393c3ea00295a25bb581785755bf，四原件已核，原81仍71/81及12延期不改。connect真实4/4检查通过，工具2轮/调用1次/额外0次，实际首required/次auto；精确k3.1-pro/high/推理回传及1594字长答通过，计量factor1.15；接入累计8/20含旧4。随后同进程立即启动core30，T05在首POST前被本地LifecycleBinding的旧k3/k3-256k白名单拒绝，映射ledger_unavailable；下游CoreObservation还使用K31批准没有的equivalent属性，尚未走到。core新增真实0、T05 incomplete/score=null，其余未运行，不能记0/30失败；原report和k31_results incomplete保留，key已清，不重试/换control/换账本。唯一安全摘要docs/v4/eval/k31-r20-cb7a00d706f047d4b810a0f62f6ef683.json；代码树不改，待必要新bug裁定。


- [x] (2026-10-24 18:36 +08:00) v18/R18代码片在独立r18分支e9c82f4已推，唯一代码/定向证据索引为该提交本计划18:26/18:29（旧3必要兼容过、新9过、追加2过；首Mock参数违schema的8失败保留，不合并计一次绿）。该e9新R11 18:30:44–18:33:40完整通过后，原R17账本/新control真实重跑2次，因第二次同名同参数重复正确停止；含旧2次累计4，core30未启动、key清除。唯一公开结果为本树docs/v4/eval/k31-r18-aa6eb26c861e487c877e392e7eb2ba69.json，原始PG/proof在r18/private，不重复抄录。

- [x] 2026-10-24 13:45 +08:00 R16接入/可信核心选择与R12必要代码已接：固定4物理检查（工具往返/U39/high、长输入实际计量及Z1系数、中文长答完整结尾），PG重读证明/独立core-k31批准、主/外部评分精确K31及系数注入；新tools.eval.k31_cli和runner --connection-proof、--fresh-questions-from、无正文rollup入口。尚未整合最终同源候选，禁止真实运行；现有R11 b008不套新代码。
- [x] 2026-10-24 13:45 +08:00 必要验证原件（根均读metadata/XML/log，不合计成一轮）：private/safe-narrow-c61c8bc9fcba4e9984fde820467737c9为2过1败（成功协议/PG可信选择及20上限通过，身份错只停本请求未持久全停失败）；修后2474c766f6354416981e196e70e9bfb5为6/6（4.32s，含5旧终止兼容）；2bfbdf8fafa94afb8fb65fa21fc828d3为6/6（2.08s，R12+旧judge/阈值/实际tokenizer启动）；a60d3756c8be41d485206e6a2c2977fe为2/2（1.03s，浪费计数汇总+旧过期/复位）；08eb916531c643c2b3442f7d8636e677为3/3（.61s，固定待跑集+旧禁任意子集）；700e976e4b4949c085888b280f274950为1/1（.57s，target额度后不进judge）；f7866d298b42483289c22639ed85e42b为2/2（1.30s，真实CLI缺中央0POST、R12实际CLI validate仅取未完成两题）。22e0c527cd3745a2acec2bf27e47bc63的首次测试导入collection失败保留，移入已有models测试包后才执行成功。所有真实模型/服务器/外发0。

- [x] 2026-10-24 13:20 +08:00 必要源绑定修复：runner源指纹纳入config/models.first-release.yaml，防止旧配置proof复用于改动后的首发模型。新增定向1/1（0.14s），唯一原件private/safe-narrow-baa628682dba4ccf8ae0f4b4b54671dc；不重跑已绿脚本，最终候选须重新绑定。非模型调用、服务器、外发均0。

- [x] 2026-10-24 13:19 +08:00 R16必要接线第一片：R11派生69门+四组原报告消费、同HEAD/source绑定、独立K31接入批准与中央20物理/10每批跨重启约束。隔离PG/Mock必要6/6（3.46s），随后新增路径穿越拒绝定向1/1（0.19s）；原件分别private/safe-narrow-d5f29485a8534711a7fb2279e98369d6与9fc66e0659e2407d8d3542deab3ca294，根已读metadata/XML/log。真实/服务器/外发0，真实CLI、可信核心选择与R12尚未完成。

- [x] (2026-10-24 12:31 +08:00) R16首发独立配置与OpenAI原生wire/身份消费者离线片完成，v13已读，单代理；原c74排13:00树不改。首链8新+2直接旧U39兼容共10/10（0.18秒），为控制函数≤60提取既有parser调用后仅两条受影响行为2/2（0.14秒），固定服务资产显式MODELS_CONFIG接缝必要一条1/1（3.14秒，真实本机PG）。根读各metadata/XML/log；不是真实接入、最终候选门或Linux通过，真实请求0。
- [x] R16新接入/可信选择器与R12题级incomplete处理代码已实现并有必要离线证据；待最终集成同源脚本门、CI及Claude真实执行，旧两模型证明始终不能授权K3.1。

- [x] (2026-10-21 01:31 +08:00) 修复候选本机4ec0d978→远端03230c6bd180305fa8b4dfd47f8f8a5ae8e9677c，tree2918b79c4d8580adc690112373b1234084715f6f。精确头CI运行39462173453、Core job118764176145及全部步骤success，含旧Core/计算器、前端、v4框架和ModelPort合成覆盖。旧dedce109失败留档，不以定向修复替代完整结果。真实256k等价、P1b与P3集成和部署仍未验证，阶段未完成。

- [x] (2026-10-21 00:56 +08:00) 精确CI失败审计：dedce109的Core553项只有冻结legacy sha失败。查明5ed56de给两个冻结替身新增离线标记，恢复原始字节；manifest/严格断言不动。两文件逐项Git候选blob等于03514f7原blob，11源文件/AST102一致，architecture6项/0.693s通过。

- [x] (2026-10-21 00:07 +08:00) 第四切片v3旧实际HTTP收口：未显式model的会员默认锁256；发送前统一auto/high、去旧1024预算/采样、合法单工具选择、严格单新user，推理/工具历史零POST拒绝并要求规范ModelPort。窄目标47+19subtests/2.97s；00:06窗口宽回归1030+19subtests/101.24s通过、0skip，真实模型0。

- [x] (2026-10-21 00:00 +08:00) 人工scope/D2第三切片：收据新建0600或Windows私有DACL+fsync、不覆盖、写盘失败保留PG批次；只读加载已授权场景并接eval/probe物理lane，中央时钟独立于评测冻结时钟。六角色默认锁k3-256k/high/replay且旧KIMI_MODEL不降级。首组58/1.90s，最终含旧subset正反例75/14.10s通过；宽回归1002通过/1旧fixture失败已定向修复，不计全绿，真实请求0。
- [ ] (2026-10-21 00:00 +08:00) 下一切片：历史ConfiguredModel未显式model的会员默认锁256；旧1024 thinking物理入口改走规范新端口或失败关闭，保留显式冻结E1历史身份及未运行产物。

- [x] (2026-10-20 23:45 +08:00) 旧HTTP/人工门第二切片：ConfiguredModel同中央PG、退役Hermes/compare实际HTTP失败关闭、真实TTY匹配句逐批授权CLI、Code漏flag仍绑定critic完成；目标59通过+19subtests/11.51s、零skip，既有Charts补实际验证；真实供应商0。文件再次交root冻结。
- [ ] (2026-10-20 23:45 +08:00) 下一切片：eval/probe可信授权scope接线与收据引用；root另准备≤20等价脚本。CLI只发短时PG授权，不等于E1可运行，旧冻结E1执行身份不得冒名恢复。

- [x] (2026-10-20 23:27 +08:00) 中央HTTP接线第一切片：显式账号位置、可信构造角色/运行scope、双协议每次物理重试 acquire、SSE用量与错误持久化、close/cancel释放、终止后零POST完成。新18项含13真实隔离PG，最终八模块295/6.13s通过；真实供应商0，文件交root冻结提交。
- [ ] (2026-10-20 23:27 +08:00) 接线剩余：旧ConfiguredModel、退役入口拒绝、eval/probe可信scope、真TTY人工开始CLI及≤20等价脚本；本切片不算所有HTTP入口闭环，完整回归/CI/真实256k验证/部署未完成。

- [x] (2026-10-18 23:34 +08:00) U39规范消息/角色策略子片：私有完整content原序回传、独立签名/空thinking/redacted、双协议真实user边界、Kimi缺签名诊断、绑定角色与默认high未实测元数据已实现。新增5模块74项，定向363/1.36s、最终models+foundation810/65.66s通过；12Python文件静态边界通过，源码冻结。旧两fixture仅补stop，原断言不变；U38冻结13/13源hash不变。
- [ ] (2026-10-18 23:34 +08:00) U39剩余：YAML配置/采样能力启用、准确effort wire/low效果探针、用量账本effort持久字段、probe/eval报告头和P3私有消息接线尚未完成；真实供应商0，不切换实际主模型。U38中央入口/部署与人工启动门仍未闭环。

- [x] (2026-10-18 23:02 +08:00) U38中央核心首切片：0008、显式账号位置/UUID、真实PG双槽/滚动预算/份额、持久全停、逐批一用授权、人工unknown恢复已离线验证。新增79项（48真实PG/31纯契约）包含在最终models+foundation共736通过/74.13s内；Ruff指定规则、format、AST限制、UTF8 LF、diff通过，源码冻结。
- [ ] (2026-10-18 23:02 +08:00) U38集成剩余：中央DSN/schema/账号身份部署、runtime配置装载、所有物理POST入口/重试/评测/探针接线和用户在线逐批启动入口尚未完成。U39完整回传及真实256k等价仍未完成；夜间真实调用（含探针）为0。详见[核心子范围证据](../evidence/P1b/2026-10-18-u38-central-core.md)。

- [x] (2026-10-18 16:50 +08:00) 阅读 P1b、P3 增补及索引 §4a；先建立 task 草案，真实请求为 0。
- [x] (2026-10-18 17:34 +08:00) M0：P2精确头CI绿并合并，建立`v4/p1b-k3-hardening`与独立工作树，正式落盘本计划。
- [x] (2026-10-18 17:58 +08:00) M1离线首切片：78项HTTP/SSE合成分类与真实adapter边界、统一类型/动作、受限公开诊断、单层retry/fallback、typed eval停止兼容；真实供应商行为未验证。
- [x] (2026-10-18 17:58 +08:00) M2配置子项：会员K3禁关思考的静态/effective env/resolve/直接adapter闸门，合法None与非会员/非K3契约保留。
- [ ] M2剩余：U39完整推理/签名回传、effort锁定、采样移除、工具选择及1.8MB体积守卫未完成。
- [ ] M3：0008、真实 PG 用量/停止状态、消费模块线 quota_guard、所有调用入口接线。
- [ ] M4：人工分批评测与探针启动门、报告身份与 k3-256k 候选配置。
- [ ] M5：用户明确开始后运行获授权的探针/等价子集，再决定是否具备实际切换证据。
- [x] (2026-10-18 17:58 +08:00) M6本地证据：Core553/638.777s、models511/75.04s及903/944约95.66%、v4918/153.58s零skip、脚本80+48/10.72s、transport+PG92/2.72s；已写离线回执。Core时点早于最终非会员402窄改，最终models/v4另覆盖，不把日志绑定同一源码瞬间。
- [ ] M6阶段门：代码与证据由root统一发布至草稿PR #9，精确头CI未核实；保持阶段未完成，不自行合并。

- [x] (2026-10-18 18:22 +08:00) M2a离线请求预检：K3 named/none（含无tools）零POST拒绝、单工具required、纯文字省略tools、sampling_fixed最终体过滤，以及httpx实际JSON字节>1,800,000预发拒绝已完成；新增122/0.30s与8个相关既有模块244/1.22s通过。六源码/测试冻结，证据见[请求预检子范围](../evidence/P1b/2026-10-18-request-policy-slice.md)。
- [ ] (2026-10-18 18:22 +08:00) M2闭环剩余：此前17:58记录中的工具选择/体积预检已由M2a覆盖，固定采样仅能力开关实现完成、YAML启用未做；完整推理/签名、缺签名回传与计数、effort、U38/0008/全部入口、人工批门、真实探针及实际256k切换仍未完成。未重跑全量/覆盖率/CI，P1b阶段未完成。

- [x] (2026-10-18 18:29 +08:00) M2a兼容收窄：root采纳独立复核，默认1.8MB仅K3（与工具选择共用is_k3）；非K3无显式配置保留旧大包行为，显式限额/无效值仍零POST拒绝。两协议补对照后新2模块138/0.31s、相关旧8模块244/0.96s；Ruff/format/AST/diff通过，最新六文件hash见M2a证据文末。
- [ ] (2026-10-18 18:29 +08:00) M2a后续阶段边界不变：仅本子范围382项，未跑coverage/整库/PG/CI；完整U39、YAML/模型配置、U38/0008/全部入口、人工批门、真实探针及实际256k切换仍未闭环，P1b阶段未完成。

## Surprises & Discoveries

2026-10-24 19:43 +08:00：中央M01 status unavailable不等于已知HTTP503，通用报告把非STOP_REASONS内kind归为provider_http_error；历史诊断不包含HTTP/type/message，不能用耗时11.94s外推超时。模型传输错误边界明确不保原cause/rawbody，当前只能诚实报告unknown。


2026-10-24 19:32 +08:00：v23第二次接入已恢复通过，旧unavailable不是模型协议不兼容；真实core已越过原本地身份门进入中央物理批。接入累计13和核心批7是不同计数，禁止把13作为总窗口量。


2026-10-24 19:16 +08:00：v22实际重新接入只发1请求即unavailable，中央物理1已完成、无stop/reset；无响应model可核，不能把网络/接口不可用说成本地白名单阻挡或额度拒绝。旧8继续保留。


18:53：接入通过后第一次触达core，LifecycleBinding仍硬限旧模型；下游CoreObservation亦旧equivalent接口。此处账本可读、inflight0，ledger_unavailable并非供应商额度拒绝。


2026-10-24 18:36 +08:00：真实两轮签名完全相同且model/high/推理存在均正确，重复熔断不是供应商403或额度问题。现有单工具auto→required与value固定enum共同约束了探针，不能把失败直接当模型不兼容或根据2次探针推算总体倍率；这两个生产策略/真实schema本片都未修改。

2026-10-24 13:45 +08:00：R16实际PG反例发现旧bad_request不属于中央持久停止类，单有error.global_stop不足以封住其他进程。身份异常现保留物理bad_request原件，同时使用既有permission_error人工解除类持久全停；无新增PG枚举/迁移。已知reset的snapshot原datetime亦改ISO字符串，避免quota报告序列化丢失。冻结脚本/旧默认模型不改。

2026-10-24 13:19 +08:00：R11的原core报告保留incomplete及延期失败，不能消费旧全81门或仅信派生计数。新消费器重读四组原报告、固定case集合/零外发/同源及X02契约；实际b008原件只读兼容核验通过，不发批准、不重跑脚本，也不将旧候选证明套到新代码。

2026-10-24 12:31 +08:00：旧turn_policy的high只表示服务器默认，没有发送参数；仅换YAML会让K3.1实际使用默认max。旧done.model是请求值也不能证明响应身份。因此新独立profile只用官方OpenAI原生Chat Completions、显式reasoning_effort=high，首响应必须声明精确model，后续声明若改变也拒绝，空响应同样不走协议重试。旧k3/k3-256k响应合同不强加model字段；尚未验证Anthropic K3.1的high wire，故该路径发送前拒绝，保留旧Anthropic行为。

2026-10-21 00:56 +08:00 / CI失败不是Windows CRLF：`test_quality_v6.py` 与 `test_review_v6.py` 在5ed56de各增加 `_zhiming_offline_transport=True`，因此真实Git blob已经不同于冻结清单。其余9源文件原字节匹配。CI只读取这两份文件做AST/hash，不执行其退役控制器，无需改冻结替身来允许离线传输。

2026-10-21 00:07 +08:00 / 仅给YAML锁256仍漏ConfiguredModel环境默认，且旧body继续发送1024预算不能只靠“历史”标注。故默认路由和实际send前请求规范同时收口；旧接口没有规范助手回执，连续工具历史明确拒绝，依赖RuntimeRouter切至ModelPort，不冒称多轮兼容。

2026-10-21 00:04 +08:00 / 旧subset正例暗依赖D2之前默认k3；新默认256必须拒绝历史子集，另显式历史fixture保留原预算和绑定断言。宽回归错误地在00–15窗口外启动，已向root报告流程错误，后续近千项范围同样按该窗口。

2026-10-21 00:00 +08:00 / 收据ID属于能力元数据，普通open(x)在POSIX可能644，故改为exclusive 0600+fsync；Windows在写内容前核当前用户SID并施加只允许当前用户与SYSTEM的显式DACL，父目录ACL只哈希审计。已真实Windows+PG验证。评测全局FrozenClock原会影响中央准入时间，runtime显式SystemClock解耦；场景时间仍冻结，不依赖本机Tokyo时区。

2026-10-20 23:45 +08:00 / 第二切片发现：退役控制器仍保留真实HTTP，不能仅称非生产入口而漏掉；现实际transport失败关闭，离线无HTTP夹具显式标记。已知Code endpoint漏membership时传输会识别会员，因此ModelHandle也必须按相同身份绑定critic，避免默认primary误拒。旧非会员403测试原继承本机KIMI_MODEL，已固定合成非会员model，保留诊断断言并新增k3 proxy零POST反例。

2026-10-20 23:27 +08:00 / 物理入口盘点确认：只接Registry会漏旧ConfiguredModel，旧hermes/compare也仍有HTTP代码，因此分切片列已接/退役待拒绝/尚缺。直接adapter原可用调用参数自选角色；新守卫必须在可信构造时绑定，测试夹具随新契约补绑定而不删U39 wire断言。OpenAI nested cached_tokens 原在safe_usage被丢，本次在实际permit内归一记录；private_content与推理不落用量表。

2026-10-18 / U39规范消息发现：旧flat reasoning与signature会合并多块签名、丢start初值/空文本签名/redacted/原内容顺序，不能无损重建。新增private_content规范回执作为回传依据，flat兼容视图保留，私有字段与StreamEvent数据不进入repr；原text/tool_calls与规范回执不一致时发送前拒绝。单凭cycle字符串相同仍可能带回最新user之前的旧推理，因此双协议再加真实user位置边界。

2026-10-18 / U39夹具：test_protocols.anthropic_record缺thinking stop、test_request_policy_wire.wire_model缺text stop。root逐类批准只补两条官方SSE闭合事件，全部旧断言保留。首轮343/363非全绿，补后363/363；最终810包含全部相关原保护与74新增。官方通用Anthropic签名格式不证明Kimi会员缺签名已实测接受，二者在证据中分开。

2026-10-18 / U38开工：运行配置中尚无runtime.yaml，因此先提供显式DSN/schema/account_id/ledger UUID的核心接口，不从任意业务库推断中央身份。账本部署拓扑及所有HTTP入口接线仍待后续交付；现有eval MemberBudget不冒充生产中央守卫。物理发送前持久reserve，即使进程崩溃也保守计入窗口；reserved并不谎称已确认供应商收到POST。

2026-10-18 / U38恢复发现：被杀进程的PG session锁会释放，但已reserve的结果无法确定，必须保留预算。新增显式人工close_abandoned_batch：同时持有两个空闲槽才把旧pending记unknown并结束批，不退款、不重发、不清全局stop，20分钟间隔仍持久生效。首轮Windows强杀用例清理Event曾阻塞测试退出；只停止本次pytest进程，修测试清理后多进程回归通过，未停启共享PG；两份严格匹配本次合成case/初版0008校验和的遗留schema已清理。

P1 的实际物理 POST 计数由 ContextVar hook 提供，旧 ConfiguredModel 仍是 E1/v3 默认路径。仅给 Registry 加守卫不能据此声称所有会员入口已覆盖；必须列出旧适配器、重试、评审、探针和 runner 路径并实际验证。若最窄接线超出增补列出的文件范围，先写清设计冲突与候选改法，不暗中放开范围。

旧 E1 已准备的 k3 冻结清单是历史准备物；未运行、没有成绩。新 D2 及唯一守卫生效后需重新准备可验证执行身份，不把旧清单改名为 k3-256k 实测，更不把不同模型分数直接相减。原无人值守 coordinator 已禁用。

自定义factory曾让adapter四次重试乘以Registry四轮，纯MockTransport复现16POST。现在Registry每次调用暂时将StreamingHTTP.max_retries置0并finally恢复，失败4次、成功2次、取消1次均有回归；visible后不重播、仅显式非会员fallback与总deadline保留。

HTTP402会员专项重试最初扩大到非会员，最终窄改保留非会员BadRequest/no-retry并加反例。最终models511/v4918在窄改后重跑；Core553是同切片回归过程、在该窄改前完成，不能把各日志宣称为同一瞬间源码。覆盖以903/944精确语句数记录，显示96%，95%门通过。

合成矩阵正式从ignored的tests/v4/models/fixtures候选路径移至AGENTS允许的tools/eval/fixtures/u37_error_matrix.json，78项已跟踪。内嵌source_design_sha256实际绑定task的84项派生离线设计矩阵前身，已核实92396c...；大脑原P1b提示词hash另列，不能混称。

2026-10-18 / M2a请求边界发现：JSON字符数或消息正文大小不能代替真实HTTP包体大小，中文UTF-8、转义、图片与工具schema都要计入。现在先client.build_request生成httpx最终JSON字节，再检查request.content，最后client.send同一个Request；体积拒绝、序列化失败在before_provider_request与request_count之前发生，122项新增替身测试含精确边界与零计数断言。非K3的原none/named、普通采样协议契约由相关旧测试继续保护。六文件的完整hash与具体覆盖见M2a证据；这些结果不是U38中央PG守卫证据。

2026-10-18 / M2a独立只读复核补充：共用transport默认1.8MB限额当前覆盖非K3，非K3原先的大包行为因此改变；现有非K3测试仅保护工具选择/采样字段，没有非K3大包负对照。增补D共用保护与“保留非K3旧契约”的范围由root核对；若后者含体积行为，应另行收窄并补测试。本子任务保持六文件冻结，未自行扩大修改。

2026-10-18 / M2a兼容复核已解决：首轮共用transport无条件加默认1.8MB会改变非K3原大包行为。root明确要求保留该旧契约，因此默认限制现按K3身份收窄；两协议新增“非K3默认大于1.8MB可发送”与“显式限制/无效值零POST”对照。最终httpx字节→size→meter/count→send顺序保留；源码再次冻结并通知eval只读复核。此修正没有改变缺签名、完整推理、effort或中央守卫的未完成状态。

## Decision Log

2026-10-24 19:43 +08:00：依v26第3条分类不明提醒，保留前6有效结果，不擅重试M01/改原JSON stop_reason/换账本/删除批次。v25扩展suite需代码按板跳过。


2026-10-24 19:32 +08:00：复用原R17 ledger，固定退避无随机抖动；当前新source独立R11与connect绑定，不复用旧proof。核心若中断只原report未完成题新run；等待不持额外key，执行子进程finally清。


2026-10-24 19:16 +08:00：保持448/e708及旧证明原件，未改SHA绑定或复用旧成功proof，不重试；未启动core无报告不造rollup，累计请求9/20。


18:53：保留v21新候选及所有原件；不把未执行核心题记失败，不更换账本或自动重发connect，不绕旧生命周期身份门。按板仅修裁定bug，当前等待core模型绑定裁定。


2026-10-24 18:36 +08:00：按R18失败立即停、由大脑决定后续，不擅自退回旧模型或再建control。旧账本与四条物理记录保留，额外执行工具0与额外工具请求1分别报告；泛化第3/4轮正例仅为Mock显式变参测试，未放宽真实schema。新代码同源R11独立重绑，不套旧d167报告、不动正式在途full回归。

2026-10-24 13:45 +08:00：R12只对新sealed K31 core scope把停止题标incomplete/score=null，不计成败；旧评测契约不变。--fresh-questions-from仅接受同候选/同源、已知5h恢复窗口的原报告，并从原计划剔除已完成题，显式新调用/新run/新期限；仍禁--resume，原过期run零POST。rollup保留中断浪费，不重签、不延长旧期限、不做累计预算新账本。

2026-10-24 13:19 +08:00：R16接入使用独立sealed K31ConnectionApproval和k31-connect中央阶段，不能从旧两模型等价布尔升级，也不能由接入批准进入core。沿用现有PG批/在途账本；不新造同run续作账本。新增纯策略反例与实际PG+HTTP Mock验证20次跨批/重启硬上限及旧模型0POST拒绝。

2026-10-24 12:31 +08:00 / 按R16补最小消费者：新增config/models.first-release.yaml，旧default/v3文件不改；审核资产共同env最后固定MODELS_CONFIG至同候选新profile，既有资产测试只新增一条对应断言，不弱化原断言。新错误沿原BadRequest分类和全停动作使Registry不重试/不fallback，评测TrackingPort沿原provider_http_error停批，不新建中央stop类型或重签旧批准。未把此静态配置/Mock成功当账号权限、effort实测、K3.1分词器等价或正式新模型批准。

2026-10-21 00:56 +08:00 / 恢复而非重签基线：两个文件恢复到03514f7原始字节；不改manifest哈希，不归一化/忽略新增行，不弱化102-ID或目标场景断言。仅对这两个已冻结文件加`.gitattributes -text`，保留普通可变tests的text=auto/eol=lf。退役网络守卫及正常非冻结替身的离线标记不变；无需新legacy执行harness。root统一提交发布，CI待精确新头复核。

2026-10-21 00:07 +08:00 / 第四切片按root裁定：真实旧请求必须采用当前K3规则，不能仅记录历史。构造显式历史k3身份可保留，默认未显式会员model锁256；旧入口只允许单条新user并一次submit，禁止历史继续调用的影响在证据明确，未来多轮用规范ModelPort的完整原序回传。非会员旧契约不变，不猜effort控制。

2026-10-21 00:00 +08:00 / 第三切片：读取收据不创建/续期/结束授权，严格schema、suite、场景子集与绝对有效期核验，PG每POST仍复核。收据写盘失败返回GRANT_CREATED_RECEIPT_WRITE_FAILED并保留已建批次待人工收口/到期，不自动恢复。根代理独占≤20等价脚本，本切片只改通用旧probe入口，真实模式必须已有TTY授权收据；取消关推理比较，none/named继续零POST拒绝。默认Registry按D2锁256，配置状态标policy_locked_unverified，不能当实测。旧默认配置测试k3断言按D2改256；人工TTL断言从精确900改899–900秒，因SystemClock两次读取相隔微秒，仍保护15分钟上限。

2026-10-20 23:45 +08:00 / 第二切片：所有仍可调用的退役Hermes/compare物理POST明确拒绝真实HTTP，保留算法与显式离线I/O回归；冻结production_v5十文件不改。五处测试夹具仅声明无HTTP传输，未改业务断言。旧legacy_other_403例补固定synthetic-nonmember，保护旧非会员诊断，不让宿主KIMI_MODEL决定测试合同。真实TTY是创建批授权的必要条件，参数/环境不得代表确认；每次新批仍需用户输入准确句，CLI不发模型、不清stop、不自动下一批。

2026-10-20 23:24 +08:00 / 夜间接线：中央账本角色从端口可信构造快照取得，不能由 stream(role=...)、模型参数或请求 headers 提升。现有 U39 六角色 wire 用例原本默认 primary 构造后在 complete 切换角色；其保护的是六角色均用 documented server_default/high、不发送猜测参数、保持完整推理回传。只给该夹具补 role_binding=role，所有原 effort/wire/metadata 断言保留；新增运行时切角色零 POST 反例。初轮因旧夹具10失败/194通过，修后需复验，未计绿。纯协议 MockTransport 无真实网络可不配置中央PG；守卫集成必须传真实隔离PG guard。真实会员HTTP缺显式中央身份一律零POST拒绝，不从业务库推断或自动创建账号。

2026-10-19 07:15 +08:00 / Codex：精确头ee2e6de的Core CI唯一失败为旧test_core_memory版本断言仍固定7（553项，552通过/1失败，658.242s）；迁移0008后预期改8，迁移序列追加8，原64位checksum检查、篡改version1后initialize/verify均拒绝及fact为空断言全部保留。定向真实PG复验1 passed/0.90s；这不代表完整CI已恢复绿，修复头需另等结果。

2026-10-18 / U39决定：内容按原index/原block类型与字段保存，thinking签名不解释不拼接后重建wire；原flat拼接仅兼容旧读取方。仅会员k3/k3-256k强制同循环回传，缺/空signature按增补原样保留并计响应缺签名与出站待回传计数；非K3仍缺签名拒绝。只接受本项目使用的text/thinking/redacted_thinking/tool_use，未闭合/重复index/错类型delta不能形成完整回执。OpenAI保留reasoning字符串及显式空字符串，供应商原tool ID不改。

2026-10-18 / U39 effort决定：已核Kimi会员模型页默认high；开放平台默认/Claude工具映射不能冒充会员Anthropic准确wire实测。暂不发thinking、旧1024 budget或猜测effort参数，primary/critic及其他角色统一server_default/high，记录effort_verified=false。Registry绑定角色，K3运行前再拒禁思考/低档或未知effort/角色越界；非K3维持旧配置合同。声明是离线请求策略，不称low/high已测；low档、实际wire与报告/账本接线保留未完成。详见[独立决策](../evidence/P1b/2026-10-18-u39-decisions.md)。

2026-10-18 / U38夜间最新授权覆盖前述模块线分工：root委派本P1b工作树独占实现中央guard及真实隔离PG单测，root不写此树；发现模块树同名文件即停该文件并切U39。核心必须显式核验数据库位置与固定ledger UUID，运行角色不可建账号或删除用量。默认60/20/20：critic占critic池，eval/probe与background共用后台池；交互可借空余额，非交互不可借。配置装载与可信角色路由尚未接线，测试中的低限额只收紧80上限。停止只人工解除；明确5h停止至少5h且仍需人工，风控/Access永久全停直到人工核准，不降并发继续。

2026-10-18 / U38幂等与兼容决定：本地80上限触发亦持久停止，窗口到期不自动发起新请求；人工clear/recovery与批次授权共用append-only一用ID账本，旧clear重放不影响后来新批/新stop，恢复ID不可跨batch复用。已观察到终止错误时，即使本机时钟回拨也先持久记录stop与结果，后续准入仍拒回拨。root批准只将test_p2_foundation两处当前升级预期7→8：保护的是保留旧数据和升级幂等，不是冻结发布版号；其余断言不改，新用例另保留schema7发行版拒schema8负例，0001–0007的Git对象和规范化校验和不变。

2026-10-18 / 用户明确决定与索引 §4a：D1 继续全部使用 Kimi Code 会员端点；总在途≤2。`concurrency_limited` 或 `Access terminated` 立即全局停止并置顶通知，优先于增补默认的仅降至1/暂停后台24小时。停止必须持久化，不自动换 key/同会员模型或定时探针恢复。

2026-10-18 / 用户决定：E1/E2 只在用户在线且本聊天明确“开始 E1/E2 第 N 批”后执行，每批≤10；夜间不发任何真实模型请求（含探针）。探针同样等用户“开始”。旧15号的自动续跑不能替代逐批授权。窗口仍≤80真实POST/5小时，目标、评审、探针、内部重试共同计数；20分钟间隔仍执行。没有授权只做离线 MockTransport 和真实隔离PG检查。

2026-10-18 / D2：主模型与评审目标均为 k3-256k，保留独立上下文。切换前要求≤20次等价子集；当前未获探针启动授权，因此只准备配置/验证门，不能宣布已实测等价或已在网站切换。新模型/effort/协议作为独立报告身份，P0 k3 成绩不直接相减。

2026-10-18 / D2上下文附加要求写入P3：目标约30k token，>120k压缩旧层，输入硬上限180k，单工具>8k摘要；每次写用量账本，连续3次>60k在汇总提醒。P1b提供输入/缓存/输出用量与错误，P3负责装配/压缩与不丢关键约束；缺供应商用量记null，不伪造精确token数。

2026-10-18 / D3-D5：准确时辰优先time_basis核对，事件反推低优先且不外部名人评测；使用时长提醒默认关闭，不登记紧急联系人；E2只跑2025子集。P1b不越界实现P7/P8，只在报告与调度入口保留这些边界。

2026-10-18 / 迁移：0008_model_usage由P1b独占，P5对应0009/0010，退役LangGraph0011。只新增顺序迁移，不修改0001–0007；若已知链机制出现真实冲突，记待决并切换其他里程碑。

2026-10-18 / Codex离线首切片：旧“一律会员429/正文quota即额度停”的断言按P1b§A替换为状态/type优先；继续保留严格403公开句1POST、隐私、取消/deadline、visible不重播、旧v3一次业务charge与repair不重开。PG shim分别测403=1物理POST、429=4物理POST；初跑430通过/1失败不计绿，修后全量重跑。非会员HTTP402保留旧BadRequest，不把会员60秒重试扩散。

2026-10-18 / Codex验收边界：本切片仅完成离线U37和U39禁关思考子项。U38中央PG账本/槽位/持久stop、U39完整回传、effort/采样/体积/工具选择、人工批次代码门、探针和实际256k切换均未完成。ErrorActions标记并非PG执行结果；最终分支ref/PR/CI由root发布后核实，不能以本地成绩宣称整阶段完成。

2026-10-18 / M2a子范围决定：只新增request_policy.py与两个test_request_policy*.py，窄改两协议和transport，不改errors/YAML/Registry/旧适配器、U38、迁移或冻结E1来源。K3工具选择在消息编码前检查，即使没有tools也拒绝非法choice；单工具required仍服从原caps，不伪造能力。sampling_fixed=true才过滤最终temperature/top_p，不在本子项翻YAML。体积默认按十进制1,800,000字节，正整数settings.max_request_bytes可配置，非法限制失败关闭；采用httpx实际序列化而非近似估算。文件首次exclusive创建、后写先核SHA256；源码验证后冻结，提交/发布归root，未经真实探针不宣称供应商协议与模型切换已验收。

2026-10-18 / root决定：P1b K3专项的默认体积保护与工具选择必须共用同一is_k3谓词，不无声新增全供应商默认限制。非K3仅显式max_request_bytes才检查；显式None等无效值不能被当作缺失而放过。按此最小改动补两协议对照，不改YAML/Registry/旧适配器/模块守卫；此前默认全端口的解释作为历史保留，当前以兼容收窄为准。

## Outcomes & Retrospective

2026-10-24 19:43 +08:00：core真实6完成3通过3失败，M01中断，其余未运行；acceptedfalse/incomplete，窗口38/核心25/接入13，三批<=10已核，密钥清。暂缺可追溯HTTP诊断，未宣称完成或stage就绪。


2026-10-24 19:32 +08:00：R22框架17/17和新同源R11完成，真实接入4通过，core30后台在途，accepted尚未形成；不提前称真实全通过或stage就绪。


2026-10-24 19:16 +08:00：R21新增PG全链/恢复定向、新R11完成，真实入口在接入1请求后unavailable停止，尚无本候选核心题质量证据。主线无服务器/飞书/外发。


18:53：v21根因修复与新R11、真实接入均通过，core已立即尝试但本地0POST停止；唯一安全摘要及原report/rollup在Progress，未验证core实际答题质量。


2026-10-24 18:36 +08:00：R18所要求的最小循环/每轮检查/重复及4请求边界/累计20预算有定向证据，新真实检查按重复调用止损。真实核心30仍未开始，不伪造k31_results或分数；等大脑对上述真实策略事实裁定。正式d167及stage/生产未动。

2026-10-24 13:45 +08:00：本轮必要代码已具有真实可用入口，但不能拿b008旧门放行新源码；接下来仅普通集成、最终候选同源脚本/CI与交接精确命令、stage必需串联。真实接入/核心30由Claude执行，本代理零真实请求；中央配置仍缺，不自动创建账户。生产/Docker/服务器均未操作，stage就绪提醒仍不发。

2026-10-24 13:19 +08:00：交接仍未可发真实请求；只完成必要门消费/接入限流底座，后续须补K31实际接入检查、PG证明可信核心选择、R12整题中断及实际CLI后再交Claude。R11冻结b008不变；本树新实现必须整合后重新绑定候选。旧模型配置/既有证明/v3未改，stage单仍No-Go，不重复通知用户。

2026-10-24 12:31 +08:00 R16离线片：主/评审实际合成HTTP请求均精确k3.1-pro/high，U39原推理/原tool ID回传、合成中文长答不丢、错/缺/后续改变身份在不可信内容前全停且无重试、空响应和未核Anthropic路径均关闭。effort_verified保持false。唯一原件均在release-prep的private/safe-narrow-b38fca028bb140a99c2d96b16b0c1f71、014798210b7e47f1b08d44d747dd95b5、3ac18992206d4d329892a42c591a3e6d；不合计成一次13/13。官方依据https://www.kimi.com/code/docs/kimi-code/models.html于本轮只读核验。真实新模型选择/≤20接入/核心30尚未执行，R11固定c74仍scheduled；本片是另树后续提交，不能套用c74脚本证明。v12停止Docker，R2新库对调工具仍缺，stage/prod执行单仍No-Go。

2026-10-21 00:56 +08:00 / 最小恢复候选完成：11份源的工作树原字节及拟提交Git blob均等于03514f7，AST精确102；architecture6项0.693s通过，diff检查通过。此前CI553项的1失败不能称绿，恢复后的远端CI尚未运行。证据见[冻结字节审计](../evidence/P1b/2026-10-21-frozen-legacy-integrity.md)及同名JSON。没有新依赖、模型/服务器/飞书请求或迁移；P1b整体仍未完成。

2026-10-21 00:07 +08:00 / 第四切片47项+19subtests窄目标通过；宽回归按00–15窗口启动，最终1030项+19subtests/101.24s通过，0skip、1既有helper警告。证据[2026-10-21-v3-wire-slice.md](../evidence/P1b/2026-10-21-v3-wire-slice.md)。失败关闭不是全多轮兼容完成，无真实模型/部署/合并。

2026-10-21 00:00 +08:00 / 第三切片首组58 passed/1.90s，包含真实PG与Windows DACL，Ruff指定规则通过。最终具体失败文件加首组75/14.10s通过；宽回归1002通过/1旧fixture失败后修正并定向复验，未宣称宽回归全绿。首轮使用缺jieba的老主树Core环境在收集前退出，改用既有P2 Core解释器后通过；没有安装依赖。证据[manual-scope-d2](../evidence/P1b/2026-10-21-manual-scope-d2-slice.md)。历史v3 body、U39旧入口收口、等价真实验证、部署、完整P1b验收仍未完成。

2026-10-20 23:45 +08:00 / 第二切片：59项与19subtests目标通过、零skip；真实三引擎固定牌用例在显式既有Charts后通过。两旧pytest helper警告如实保留。证据 [2026-10-21-legacy-manual-slice.md](../evidence/P1b/2026-10-21-legacy-manual-slice.md)。旧body/算法和新端口U39均保留，eval/probe接线/等价/CI仍未完成，P1b不作整阶段完成结论。

2026-10-20 23:27 +08:00 / HTTP第一切片：295/295目标回归、Ruff通过，真实中央PG只用本机独立schema。已接双协议每物理尝试，未声称旧v3/E1/探针全覆盖，未运行真实模型。证据为 [2026-10-21-http-guard-slice.md](../evidence/P1b/2026-10-21-http-guard-slice.md)；后续先补旧入口与人工门，所有发布仍由root处理、PR9草稿不合并。

2026-10-18 23:34 +08:00 / U39子片可独立审查：以U38本机提交2cb0277a282431ddcf7d8392fd885ce1c8eff41b（远端等价18352da4）为基底，5端口/codec/helper、2旧fixture闭合增补与5新测试已冻结；最终810/810通过65.66s，新增74项均在内，Ruff完整规则/format120/AST/UTF8 LF/diff通过。精确来源见[结构化记录](../evidence/P1b/u39-turn-validation-2026-10-18.json)，命令/§11边界见[子片回执](../evidence/P1b/2026-10-18-u39-turn-slice.md)。没有修改模型YAML、旧适配器、U38源码、P3或服务器；probe/eval头/账本effort/真实效果/全入口/部署仍未完成，不能宣称整个U39或P1b验收。当前未提交，由root统一发布。

2026-10-18 23:02 +08:00 / U38核心可独立验收：最终P2 Core解释器在P1b cwd运行models+foundation为736/736、74.13s、0skip，其中新增6模块79项（48真实隔离PG、31纯契约）。同账号三进程/第三个零POST拒绝、进程重启stop、滚动80保守reserve、降权角色、迁移8、人工unknown恢复和操作ID重放均有证据。源码/测试13文件hash与静态核验见[结构化记录](../evidence/P1b/u38-central-core-validation-2026-10-18.json)，命令和边界见[§11子范围回执](../evidence/P1b/2026-10-18-u38-central-core.md)。此前42/33.45和733/70.15是中间源码验证，不能替代最终身份。未跑整库Core/v4、coverage、scripted评测、CI或真实供应商；全入口/中央部署/人工启动入口/U39/256k切换均未完成，不把U38核心成绩称整阶段完成。未提交/推送/合并，交root统一核对发布。

离线首切片已有生产代码与证据：本地代码2cf6b1f1edefac46e2b5d035484713326eacf7d0，等价远端不可变代码对象be8119e475034306681b6d168ab49073b2a23b76，代码tree ff652a9d1e4a8b64cd83e364aebf10be1234cb47。U37分类/当前链动作、统一retry/fallback、typed eval停止及禁关思考配置闸门已离线验证。Core553、models511/约95.66%、v4918、脚本80+48、transport/PG92的结果与源码时点见 [离线验证说明](../evidence/P1b/2026-10-18-offline-slice.md) 和 [结构化证明](../evidence/P1b/offline-validation-2026-10-18.json)。

阶段未完成，当前没有新迁移、U38中央持久守卫、完整U39或真实探针结果；没有实际256k切换。旧E1自动入口仍禁用，旧k3冻结仅历史未运行；后续新256k来源另建身份。代码与证据随本提交统一发布至草稿PR #9，精确头CI待核验，当前不合并。回执 [receipt-daytime-2026-10-18.md](../evidence/P1b/receipt-daytime-2026-10-18.md) 逐项列明剩余，避免离线全绿被误读为完整验收。

2026-10-18 18:22 +08:00 / M2a新增结果：基底及测试时HEAD为a0788aaf86fb278e95cd9a9c174b8fa877862dde，六个未提交源码/测试hash锁定在[2026-10-18-request-policy-slice.md](../evidence/P1b/2026-10-18-request-policy-slice.md)。新增122项/0.30s、相关既有244项/1.22s及Ruff/format/AST限制/UTF8 LF/diff检查通过；仅MockTransport、指定P2 Core、清空凭据并关追踪。未跑coverage，本次无新增覆盖率数字；不能借用先前95.6568%或全量日志作为M2a后的重新证明。U38、完整U39、YAML/模型配置、人工批门、探针与实际256k切换仍未闭环，P1b阶段未完成。

2026-10-18 18:29 +08:00 / M2a最新复验：默认体积限制已收窄至K3，非K3默认大包兼容与显式限制失败关闭均有两协议证据。新2模块138通过/0.31s、相关旧8模块244通过/0.96s，Ruff/format/AST/UTF8 LF/diff均通过；最新六源码/测试hash和具体结果追加在[M2a证据文末](../evidence/P1b/2026-10-18-request-policy-slice.md)。首轮122/244及旧hash保留为历史，不当作最新源码身份。未跑coverage/整库/PG/CI，U38/完整U39/人工批门/模型切换仍未闭环，阶段未完成；提交发布归root，独立eval复核已通知、结论待回报。

## Plan of Work

M1以官方原文或历史受限公开诊断为错误夹具依据。403保留严格permission_error+usage limit规则并扩展monthly/concurrency/access terminated；402一次60秒重试、429按rate/overload退避、400区分reasoning/size/token/content，流式同分类。诊断只留允许字段与审核过的公开提示，不能把任意响应前240字带出边界。所有终止型错误不重试/不换同会员模型。

M2先查官方 Kimi/Anthropic effort 字段；不能凭猜测新增参数，缺文档且无授权探针时采用服务端默认high并明确fast未验证low。会员k3*禁关思考；固定采样不发temperature/top_p。工具循环回传原始完整规范助手消息及推理/签名，新真实用户轮关闭旧循环；缺签名只计数，真实效果等待授权探针。禁止named/none且0请求，纯文字不带tools，单工具强制required。请求序列化>1.8MB预发拒绝。

M3用量表每个物理POST一次（含失败与重试），无正文；PG专用连接持有会话advisory槽，交互预留一槽，其他通道一槽，总在途≤2，不能持owner业务事务跨网络。预算份额/借用用真实并发PG验证；monthly、风控、Access terminated全局持久停，人工解除是显式操作。部署授权同步新表。接口guard.acquire/status/critic_allowed/background_allowed，与模块线真实代码核对后接线，不编造通过。

M4评测执行单批即返回，不通过--follow或定时器继续下一批；用户授权批号、场景上限、已完成场景、执行身份和共享账本绑定，重启不自动开新批。替身测试证明无启动授权0POST、批≤10、批间隔及80窗口保护。旧报告/基线不可覆盖。新增background角色仍用会员；主/评审256k候选有明确验证门，环境model覆盖不得静默退回k3或关思考。

M5用户明确启动后，按每次具体授权执行探针，非自动串跑所有suite。E1-E4总上限40、等价子集≤20且合计真实窗口≤80，所有探针经过守卫。正文不入探针日志，只记工具完成/参数核验/签名/缓存/用量。没有结果写未验证；变差/缺签名失败记待大脑，不私换模型。

## Concrete Steps

本切片已执行离线检查，以下为可复验入口；精确结果与源码时点见evidence/P1b，不将命令列表当额外成绩：

    python -m pytest tests/v4/models -q
    python -m coverage run --source=mingjing_core.models -m pytest tests/v4/models -q
    python -m coverage report --fail-under=95
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test
    python -m ruff check <新增和修改的现代文件> --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check --line-length 120 <新增和修改的现代文件>
    git diff --check

PG明确core_test_main/127.0.0.1:55480，测试每例独立schema；Core/Charts环境隔离，清空Kimi/Moonshot钥及追踪。以上测试不能触发真实HTTP。任何真实探针命令只在用户明确开始后记录具体批次，不在计划中放自动可运行循环。

## Validation and Acceptance

增补八项逐项保留：错误→类型→动作实测表；真实PG三调用最多两在途（风控后全停）；月额度跨进程持久全停与人工解除；禁关思考拒启动；E1–E4探针真实结论；所有runner物理调用在用量表且lane=eval；CI及模型覆盖率≥P1约95%；计划与§11回执。D1持久全停/人工批门、D2新模型身份及上下文账本映射还须分别落地并补回归。未获得真实启动授权时第五项标未验证，不能宣布整阶段完成。

对应19号候选场景K01–K03、K05的端口/守卫部分；07原有L01、X03–X05保持旧协议、恢复、取消回归。真实场景新定义归v2.3候选，不修改已冻结v2.1八十场景或分数。

## Idempotence and Recovery

后续M3的用量写入与请求预留必须有稳定attempt_id，崩溃不能释放预算重发绕计数；在途槽由PG连接死亡释放，停止标志持久保留。重试每次都单独记数，排队未POST不当作已完成请求。这些PG守卫与迁移要求尚未实施；迁移只能先在合成库前向验证，旧版本拒不认识schema。回滚先停新入口/owner回v3，实际stage迁移与生产回滚另需具体授权，本轮不执行。

## Artifacts and Notes

正式产物为本ExecPlan及evidence/P1b/2026-10-18-offline-slice.md、offline-validation-2026-10-18.json、receipt-daytime-2026-10-18.md；探针报告尚未生成。task旧草案保留为历史。最终提交/发布/PR与CI由root负责，文档编辑者不自行操作。待用户：每次探针/评测开始；待大脑：实际协议/范围冲突及探针变差；待模块线：quota_guard核心接口交接。所有问题写汇总后继续独立离线工作，不等待。

## Interfaces and Dependencies

依赖P1/P2合并；与P3并行，P3的正式守卫接入里程碑要等P1b合并。quota_guard核心由模块线供给，主线负责真实PG集成、迁移、Registry/物理POST接线及人工执行门。模型用量与安全错误不包含任何用户原话、思考正文、请求/响应、key或完整DSN。

## U37首切片接口与旧测试替换依据

统一纯分类器`classify_error(status, payload, membership=..., surface=...)`返回旧ModelUnavailable兼容异常，新增受控kind与不可变ErrorActions。只读取完整嵌套error外壳；HTTP与SSE共表，SSE没有状态不捏造429。ModelPermissionError采用旧ModelPermissionDenied同类别名。公开诊断只保留审计句，不把任意响应前240字导出；新错误的原始正文不留在异常/日志。

主线拆分所有权：分类代理只改errors.py/provider_diagnostics.py/error_classification.py及新矩阵测试；root改transport.py/registry.py及下游eval兼容。模块线独占quota_guard.py。重试只在一个层执行：Registry构造adapter max_retries=0；直用adapter按同一ErrorActions执行。会员HTTP402最多2尝试（60s一次），非会员HTTP402为BadRequest且不重试；429/5xx/网络最多4尝试（1/3/9加抖动），总deadline/取消/可见输出进一步收紧。global_stop优先，无自动同会员fallback；没有PG接线时不能声称跨进程全停已经实施。

Decision Log补充（2026-10-18/Codex）：旧test_membership_quota_never_retry的429和500正文quota、streamed membership rate-limit和unreadable429断言保护旧“一律额度停”行为。P1b §A明确替换为状态优先的rate/transient动作；只修改这些已被新设计替代的断言，保留真实403额度1POST、隐私、取消、总deadline、不在已可见输出后重播的保护。Registry旧503两尝试用例按同一明确退避预算更新，不保留嵌套两套重试。84个先行矩阵中的未官方证实文案标格式推定，不称录制响应。

中心账本拓扑（后续M3）：所有业务库/评测/探针明确共用同一ledger DSN/schema/account scope；PG advisory锁仅DB内有效，不能各业务DB建独立守卫。拟用独立本机无正文账本数据库，配置固定ledger identity，缺配置失败关闭。每个物理attempt先预留、结束后终结，不能一complete只算一次或多层重复acquire。具体数据库/迁移安装仍未实施；不把方案当验收。

2026-10-18 / Codex：旧Anthropic流式quota正例只有无类型message=quota，按新状态/error.type优先及回显隐私规则不足以证明额度。正例换成保留已审计的permission_error+5h公开句；新unknown SSE含quota/429回显的负例单独断言不猜状态、不重试。旧probe额度夹具由429换成真实403公开额度句，仍保护恰1POST和无正文输出，429退避另由新动作测试覆盖。

2026-10-18 / Codex：合成78项HTTP/SSE矩阵放tools/eval/fixtures/u37_error_matrix.json，遵守AGENTS合成夹具路径；不强制加入被gitignore保护的tests/v4/models/fixtures。其余6项transport/local归实际执行测试，不能把纯分类通过当成PG持久全停完成。

2026-10-18 / Codex：完整模型覆盖初跑430通过/1失败，失败为旧真实PG shim仍用429冒充quota。将其参数化为403公开额度句=1物理POST、429 rate=4物理POST，同时都保留1个旧v3业务charge、失败终态、repair不重开；这区分供应商物理重试与旧业务预算，不削弱预算或服务真实路径。初次96%覆盖不计作通过，修后完整重跑。

2026-10-18 / Codex：402会员验证60秒重试仅限membership提供方，非会员402保留原ModelBadRequest且不重试；避免把Kimi专项动作扩到其他供应商。新增非会员反例；真实供应商兼容/探针仍未执行。

## 修订记录

- 2026-10-24 12:31 +08:00：v13及R16离线片、必要三轮原件与未验证边界；保旧默认/授权，更新现有runbook的v12恢复规则及F限定对象，不连接服务器。

- 2026-10-20 23:45 +08:00：追加旧HTTP/退役阻断/TTY批门第二切片证据、零skip复验、夹具显式非会员与离线I/O声明的Decision Log；下一步为授权scope接线。

- 2026-10-20 23:27 +08:00：追加中央HTTP第一切片四活节、可信角色夹具变更依据、295项证据与所有入口未完成清单；实际模型调用保持0。

- 2026-10-18 17:11 +08:00：建立并补全task草案，纳入18索引§4a与明确人工开始门；P1已合并、P2尚在完整回归，不抢先建正式分支。
- 2026-10-18 17:34 +08:00：P2合并后M0完成，补U37接口/动作与旧测试替换依据，中央账本仍等模块接口接线，真实请求0。
- 2026-10-18 17:58 +08:00：更新Progress、Surprises、Decision Log、Outcomes及离线首切片证据/§11回执，记录553/511/918/92/80+48和903/944语句覆盖；明确Core与最终非会员402窄改的时点差异、78项夹具迁移/派生来源、U38/U39剩余与发布CI待root，不宣称整阶段完成。
- 2026-10-18 18:22 +08:00：追加M2a请求预检子范围的四个活节及独立证据：122新增、244相关既有、六文件hash与实际命令；保留此前历史，明确U38/完整U39/模型切换、全量覆盖率及CI仍未闭环。
- 2026-10-18 18:24 +08:00：追加独立只读复核发现的非K3大包默认限额兼容边界，交root核对；源码保持冻结。
- 2026-10-18 18:29 +08:00：追加root采纳的M2a非K3兼容收窄、最新138+244复验与六文件hash；保留首轮历史，默认全端口问题已解决，完整阶段仍未完成。
