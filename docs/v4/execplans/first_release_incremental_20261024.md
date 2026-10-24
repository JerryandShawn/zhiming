# 核心首发：已有合成本机库备份、恢复证明与前向升级

本活计划遵循`.agent/PLANS.md`与AGENTS。所有时间用北京时间；不访问服务器，不调用真实模型或外发，由主线审阅后提交并推送自己的分支。恢复effects与原恢复计划由另一代理维护，本片不改。

## Context and Orientation

已提交起点为144b81eeed3e792221393673bd611637fbaae01f；最初M1测试包为686213f，后续各片另按真实archive与控制代码绑定，不把旧包结果挪用到新头。SourceForward原首8的候选archive为5b8397d，源worker组件及Forward补链起点为5a34b2c；这些均不是最终冻结发布包。本片复用`first_release_source.verify_source`核审核源码，复用受hash pin的`first_release_replay_worker.py`中纯stdlib导入来源及实际Python/活动依赖核验函数，实际旁账只调用候选`tools.deploy_core.export_withdrawals`。不构造旧B1输入，不借freeze/install/publish，不改变fr_restore creator硬门。

“合作性writer栅栏”指参与者写入前共同取得同一文件/PG共享锁并检查持久维护标记；本工具取得独占锁。现有应用未接此协议，因此本片不能证明全局停写或生产安全。源库严格为已存在的fr_upgrade_<operation>合成库，精确审核OID/角色/owner/连续prefix4或7，0008关系必须不存在。

## Purpose / Big Picture

本计划已从M1显式本机备份扩展到M2同call新库原始内容绑定、M3a目标证明/运行时/源双栅栏组合与前向升级，以及M3b源原生重放/回填接缝，逐片实现范围见Progress。默认只读文件校验，零PG连接、零子进程、零文件写。backup入口自身不迁移源；另显式Forward内部API的原首8已真实验证合成源4/7→8，尚无源写CLI。源worker重放组件及同call组合已有分轮真实实证；源回填在新pin同次重复上游验证去重后，受影响正反两目标于07:07首次共同2/2通过，包括closed收尾与独立完整后验。此前首1红1绿、仅原红诊断复验1红分别保留，不据后续通过倒推唯一根因。Linux、中央身份、正式恢复与发布继续关闭。

## Progress

- [x] (2026-10-24 08:16 +08:00) source-backfill 07dbf97 的 run40038236229/job120702870850 已失败：v4 4197通过/75跳过/1失败、2283.38秒。唯一 target_dml_after_mint 目标预期 TARGET_PROOF_TARGET_STATE_CHANGED，实际 TARGET_PROOF_ACTIVE_OR_OTHER_SESSION；该 OR 混合忙run/lease和其它会话，原日志不能判明哪项成立。后续 ModelPort 未跑；原始证据仅 GitHub job，不复制第二套日志，不合并该红源。
- [x] 在独立 v4/p3-wire-target-diagnostic-20261024 分片，仅给 TargetProof 原失败 gate 同一查询增加有界无正文诊断，保相同 busy/会话谓词、错误码和拒绝；不重试、过滤后台或改旧断言。新增一个真实PG诊断行为并只验证该行为；原 CI 红的未知原因继续保留。
- [x] (2026-10-24 08:21 +08:00) 同次诊断静态根审完成（helper308行/最大37；新测试59行/最大30）。指定宿主 `.venv-core` 首链在 conftest 因缺 jieba 导入失败 exit4，08:20:38–08:20:39，尚未collect或进入PG节点，无XML；原 metadata/log 保留 `private/safe-narrow-5a842771caa248abb11081fb6caa2046/`，不计产品失败/通过。仅改用既有 `.venv-k3` 宿主（jieba/pytest/psycopg 已可导入）重新执行尚未运行的同节点，不安装依赖、不修改测试或控件、不重复任何已绿目标。
- [x] (2026-10-24 08:24 +08:00) 新节点首次真实PG链1/1、95.17秒、0 skip，通过原外来连接和failed+活lease两个谓词；08:21:54.604905–08:23:30.686226。唯一证据为 `private/safe-narrow-ff677d6240634ba19a897413b360c564/metadata.json` 与同目录XML/log，根独立核原始元数据/XML；槽已释放，文件冻结供小提交。不称原CI原因已修，不重复旧绿/原CI红。

- [x] (2026-10-24 07:49 +08:00) M1限定统计observer三代码路径与新负例静态冻结后，唯一两节点07:47:43–07:48:30首次2/2通过、45.86秒：实际异角色客户端在owner视角type=NULL、在原检查admin行集中type=client backend，恰owner+foreign两PID且仍严格拒绝，源全态/维护marker/输出不变；随后原f6 capture_binding目标通过，原零I/O及血缘正文断言未改。根已复核metadata/XML及控件/调用边界；不重跑绿或扩大测试，等待小提交和新CI。

- [ ] (2026-10-24 07:44 +08:00) f6关联PR #12合成checkout dcecec3673818bd76a6934df13883c2369395a96的run40034388584/job120690168739也失败，不能与f6 push混用：v4 4301通过/56跳过/1失败/1 setup错误、2791.29秒。target_proof重建同名库目标的setup在M1握手允许2379/2381，实际额外2380/None；源漂移目标预期保留产物拒绝却提前命中会话拒绝，允许859、实际另863/None。两者尚未知身份；ModelPort/runner_v2未执行。07db与fa23新CI仍在途；X02的836 CI已cancelled（v4步成功、ModelPort步取消），不能称全CI通过，主线未取消或重跑。

- [ ] (2026-10-24 07:42 +08:00) 原正式f6fb9f1 push CI run40034381931/job120690145880亦在M1拒绝：capture_binding夹具的candidate_export握手后、ACK前允许682/684，实际多683、backend_type为None；尚未dump。584旧Core及Frontend通过，v4 4302通过/56跳过/1 setup错误，2175.91秒；fake self-test、ModelPort、runner_v2未执行。下一片只改善同次会话观察的统计可见性，保原精确PID门；实施前设计见Decision Log。两项必要真实PG测试待运行，不宣称额外PID身份或首发就绪。

- [ ] (2026-10-24 07:14 +08:00) 09173ac push CI run40031494831/job120680561852实际失败：584旧Core通过、Frontend整步通过；v4 4195通过/75跳过/1 setup错误，1206.04秒，后续fake self-test/ModelPort/runner_v2未执行。唯一错误为incremental_guard的missing-marker夹具在删除marker之前，M1 dump后精确会话门拒绝：允许1183，实际另有1186、backend_type字符串None。未知该PID来源，不猜autovacuum；07dbf97未改这一路径，尚未覆盖本次CI失败。保硬门/原日志，不自动重试CI或重复本机绿例，先切离线累计预算。

- [x] (2026-10-24 07:11 +08:00) 源回填已验片已提交并推07dbf97，工作树清洁，新push CI run40038236229仍在途。原091 archive与新工具Git身份分开；不得以本机2/2或父来源CI替代07自身检查，更不解除完整脚本与正式发布门。

- [x] (2026-10-24 07:10 +08:00) 窄修后受影响源回填正反两目标2/2通过、1103.49秒；实际archive09173ac，原同call M1/TargetProof/Runtime/Forward/replay/backfill与四次活peer观察、closed收尾及独立后验均通过。首遍回填2条真实历史，第二遍三个写计数0、完整状态不变；正式门全部保持false。负例因精确pin校验路径实际变化而必要复验，未重复无关绿项；五个Python文件Ruff/120列format通过，等待本片提交。原两轮失败不覆盖，详见Outcomes唯一证据。

- [ ] (2026-10-24 06:47 +08:00) 仅原源回填红节点复验仍红、897.18秒；新XML实证09173ac、source_backfill_3_owner_verified、session_restored=True，replay及backfill的ready/final四事件均已实际观察。不能称组合完成或独立末段后验通过；负例未复跑。先审并仅去除新BackfillPin.validate内部紧邻重复上游验证，不缓存、不改120秒或各阶段重核；随后只验证受影响原红。

- [x] (2026-10-24 06:35 +08:00) 来源9be44b9 push CI run40027420077及正式9f关联PR检查run40027607612均06:30成功；正式v4/integration普通合入9be已验源组件，保留双方两份文档追加块后推f6fb9f1，新merge自身CI待核。本树回填未验片未合，feed仍9f待新merge通过后再同步。独立X02离线故障观察片首次1/1（真实503/503/200、单逻辑步骤、原题仍红）已在另一树推83679f1，不取消其CI；未改金标/生产模型锁。

- [ ] (2026-10-24 06:35 +08:00) 新fixture安全失败侧诊断静态后仅原回填红节点复验在private/safe-narrow-f554e55fa7e945438d3606a3e747cab7运行，实际归档仍HEAD091；负例不复跑，原控件及120秒时限冻结。尚无新结论，不把本机源回填与正式门写绿。

- [ ] (2026-10-24 06:28 +08:00) 新源backfill两节点首链1失败/1通过，1175.78秒；正例在Forward抛SOURCE_REPLAY_PROTOCOL_TIMEOUT_OR_INVALID，短trace与XML无phase/peer属性，源replay或backfill具体阶段均未知。默认与错type/候选/缺replay零副作用负例已过，不重复。仅准给新fixture加失败时有限phase/peer事件及调用前candidate属性，根审后仅复验原红；生产/协议时限/成功断言不变。

- [x] (2026-10-24 06:14 +08:00) 正式集成9f2506f的push CI run40027600812已成功（06:08完成），PR #12合成检查仍在途，未混用。核feed旧5af为9f祖先后，仅正常fast-forward远端v4/first-release-integration-20261023到已集成的9f，供模块按v8读取；未新建merge、未改main/v4main、未向其他聊天发消息。本机旧feed树5af及私有报告保持，PR #16原Draft状态保留、新头检查待完成，未读取或宣称记忆2.0就绪。

- [ ] (2026-10-24 06:08 +08:00) 新源backfill两节点唯一真实整链已启动于private/safe-narrow-65c64c87ab0a411ca1f7b478a518530f，候选archive固定09173ac，控制代码与夹具冻结；尚无最终结果，不把静态或已返回阶段当验收，不另启动重复诊断/重跑。

- [ ] (2026-10-24 06:08 +08:00) 09173ac已推，后续另开v4/p3-wire-source-backfill-20261024保来源CI。独立source_backfill_pin三控件及318行新测试均已根完整审阅，Forward已按05:35设计增加首IO前精确可选pin和同活witness内replay之后回填接线；静态Ruff/format通过，真实两目标未开始，不放正式门。

- [x] (2026-10-24 06:05 +08:00) UTC新夹具规范化后仅原源replay红节点复验1/1通过、642.87秒。实测seed UTC、13项固定观察bool全true；此前未触达的fresh export/full state/中央空表与sequence、材料及正式关闭位均通过。两行为分轮成立：首1红1绿、仅红复验1绿，未重跑默认绿、不合称一次2/2；原红的具体False项仍未记录，不能补造唯一根因。

- [x] (2026-10-24 05:55 +08:00) 来源5a34b2c的push CI run40022517297已成功；9be44b9的run40027420077仍在途，未移用父结果。正式集成保持9f2506f，本轮源组合fixture规范化后仅原红复验在途，新backfill三模块/整链测试仅静态WIP，未合入正式分支。

- [ ] (2026-10-24 05:48 +08:00) 新同call源replay两节点首链1失败/1通过、868.26秒。真实组合已返回source_replay_completed并通过活PID/状态与旧fact/run/Outbox/SDK/Bob前序独立断言；随后fresh业务观察的all布尔断言失败，原异常未指出具体键，export/最后全态/中央后置断言尚未执行，不能认定组合验收。默认及错pin零副作用节点通过，不重复它；只做新夹具的时区/有限布尔诊断，不改生产或弱化断言。

- [ ] (2026-10-24 05:46 +08:00) 独立回填pin/process/worker三新文件已静态冻结（110/249/290行，函数≤60、120列，Ruff/format/AST过），根完整审阅其候选来源/逐owner事务/终态活连接接缝。尚未接Forward、未运行组件或整链，不提交成已验功能；两条新必要整链测试先静态准备，原源replay在途控件不改。

- [x] (2026-10-24 05:38 +08:00) 回填剩余两个必要core4/撤销后组件首次2/2通过、5.23秒：真实AgentRuntime产core4缺助手历史回填，及原生撤销/提交后SDK purge后再回填均有实证；只新增200行测试，未改业务/effects。fresh-process/活witness整链与legacy映射回填仍待完成。

- [x] (2026-10-24 05:33 +08:00) 已验证组件按四个小提交推送9be44b9，后续接线另开v4/p3-wire-source-chain-20261024。正式d40的push CI run40018141727/job120635838635已成功：v4 4238通过/56跳过，ModelPort970通过；此前PR合成a1e1bba的额外会话失败仍保留，非同一checkout，不据后续绿倒推根因。X08来源7996c0b的独立CI成功后普通合入正式v4/integration并推9f2506f，新merge检查待跑；未合main/v4main。

- [x] (2026-10-24 06:05 +08:00) 按05:09设计完成Forward最小可选source_replay_pin接线及分轮新组合验证；首I/O前独立pin、原活witness内真实worker重放成立，回填及正式门不扩大。

- [x] (2026-10-24 05:26 +08:00) M1会话拒绝改附同次有界PID/type诊断后，只复验CI失败prefix4目标与真实额外会话负例，2/2通过、28.60秒；负例实证伪装pg_dump的真实客户端在原失败集合。Linux失败根因仍未知，新CI未验证，不放宽门或自动重试。

- [x] (2026-10-24 05:18 +08:00) 只读核对正式integration的PR #12 CI：run40018148231/job120635461896，head d40fcd3、实际PR合成checkout a1e1bba；v4为4237通过/56跳过/1失败，ModelPort后续跳过，未作为通过。失败为M1 prefix4备份后额外PG会话，根因仍待原瞬间安全诊断。

- [x] (2026-10-24 05:10 +08:00) M3b新源worker/父子协议组件唯一首链4/4通过、381.18秒；非空原生双重放/终态活lease、无ACK不写、ACK间隙与最终真实漂移拒绝均有实证。尚未接同call SourceWitness/Forward，回填及正式门未放行。

- [x] (2026-10-24 05:19 +08:00) M3b回填effects两个必要真实PG组件首链2/2通过，4.16秒；core3精确首遍变化/第二遍无变化及后半真实写入后整事务回滚有实证。当前真实业务类组件，未接候选fresh worker/SourceWitness，core4/撤销后回填待补。

- [x] (2026-10-24 05:29 +08:00) SourceForward补链保留2通过/1新fixture类型错误；仅将该夹具对齐真实OperationalError后，唯一原红节点单独1/1通过、370.57秒，SDK实际cursor失败、未执行新增DDL、同一interrupt对象传播均有JUnit实证。原首链8/8、补链2绿1红、末轮1绿分别保留，不合称一次11/11。

- [x] (2026-10-24 04:49 +08:00) 88f1d27的Linux CI实际为v4 4163通过/75跳过/1失败/1setup错误。仅修新解释器反例的符号链接路径，并给原始捕获拒绝增加不含正文的事后会话诊断；只复验两个失败节点，本机2/2通过、33.51秒。未知额外PG会话根因仍未确认，新头Linux CI待跑，未放宽任何生产门。

- [x] (2026-10-24 04:35 +08:00) M3b物理pool lease独立基础首4节点首次4/4通过，31.93秒：真实repo嵌套与SDK直接借用同一物理Connection，closed/foreign/额外session均拒绝并永久poison。仅新helper与PG测试，未接source worker或源重放/回填，测试槽2已释放。

- [x] (2026-10-24 04:55 +08:00) 同call SourceForward原冻结实现首8首次8/8通过，04:15:19–04:54:43 +08:00、2363.75秒；真实prefix4/7均完成同call目标证明、运行时与源双栅栏组合及Core/SDK/grant。根审另发现的清理控制异常优先级和SDK setup后runtime重核仍需窄修及独立负例；不能把原首8实证冒充这些缺口已覆盖。

- [x] (2026-10-24 04:00 +08:00) 新source_postcheck只读终态组件7个独立行为按首轮6通过/1夹具错误、仅该失败节点复验1通过完成实证。真实prefix4/7执行候选forward_core、当前K3环境实际PostgresSaver.setup及grant_new_runtime后分别核owner/writer；真实字段/列/权限/sequence/事务与PID故障拒绝且不修复。两正例同JUnit记录SDK版本10→10、新增0，setup实际已调用；未接同call源写编排。

- [x] (2026-10-24 03:56 +08:00) Source guard只读基础的12个独立行为已有分轮实证（纯文件1、真实PG夹具11）：首8为2绿6红，失败6复验3绿3红，Windows同锁句柄修复后仅3红与受影响纯文件复验4绿，最后未执行4项独立4绿；不是一次12/12。实际4/7源双栅栏、维护材料与UTC完整状态核验已通过，未接源写入口。

- [x] (2026-10-24 02:00 +08:00) 实现显式backup-local与真实双栅栏、候选prefix4/7原生导出、实际PG15 dump、完整状态不变及失败保留。
- [x] (2026-10-24 02:00 +08:00) 首链8/8真实PG/实际程序/跨进程目标通过，96.61秒；清凭据关追踪，仅1测试进程，无失败、无补跑，已释放测试令牌。
- [x] (2026-10-24 02:02 +08:00) 根审新增1/1真实跨进程cooperative_writer目标通过，16.79秒：同child先实际写合成行，备份释放OS/PG锁后仍由持久marker阻止第二行；仅运行此目标，未重复8项。
- [x] (2026-10-24 02:32 +08:00) M2本机原始恢复绑定验证完毕：新受审UTC捕获→同call新fr_restore→升级前实际完整列/原字段/sequence核验；首链3绿、失败5项复测3绿、最终仅2正例复测2绿，未重复已有绿项。默认不放宽，失败保留不升级，已释放测试令牌。
- [x] (2026-10-24 03:05 +08:00) M3a第一小片仅新增中性migration_steps与严格source_profile，静态冻结供根审；没有接入入口、修改旧tools或运行测试，typed证明与源升级尚未实现。
- [x] (2026-10-24 03:10 +08:00) M3a第一小片8个新节点实证完成：首链6绿/2正例夹具比较错误，按根审仅修原prefix账本行投影后2正例复验2绿；原6绿未重跑。冻结两helper、新PG测试及本计划，释放测试令牌。
- [x] (2026-10-24 03:09 +08:00) M1→M2→8→真实候选双重放的单链已由恢复片提交并推送7e2c870，详细分段前态/后态及两次fixture错误统一见原恢复ExecPlan。为保留该父分支CI，本计划后续在同目录子分支v4/p3-wire-incremental-20261024继续；没有重置或覆盖并行WIP。
- [x] (2026-10-24 03:35 +08:00) 独立controller运行时门4/4通过，6.32秒：实际Python3.11 venv、活动Core依赖闭包及已加载PostgresSaver来源/SQL重核，返回不可由JSON重建的进程内凭据；尚未与TargetProof组合或接入源升级。
- [x] (2026-10-24 03:40 +08:00) 记录TargetProof首8节点4通过/4源夹具严格绑定失败，实际正常mint及4个关闭行为已有证据；仅捕获前按官方parse规范化fixture，原strict比较保持，后续不重复4绿。
- [x] (2026-10-24 03:47 +08:00) 记录仅4红复验3通过/1 M1握手精确session setup错误；生产strict控制未变，首4绿及复验3绿不重复，本轮唯一未触达ledger漂移目标保留真实失败记录。
- [x] (2026-10-24 03:55 +08:00) 根批准最终fence冻结后仅补ledger1+旧public M2 prefix7兼容1，2通过/147.93秒；Proof八行为现按4+3+1分轮实证，另兼容1，不称一次8/8或9/9。只在ledger新fixture安装拒绝后body-free会话诊断，通过不造诊断；已释放测试令牌，冻结本片六路径供根审。
- [ ] 后续在用户已授权的本机开发范围内，将同call目标证明与controller门组合到完整源guard及fr_upgrade前向入口，再落实源既有撤销重放与回填；尚无源升级命令。

## Surprises & Discoveries

新负例首次以真实PG角色差异复现type不可见，并在M1原门获得可见类型且拒绝，证明统计观察改动有效；没有复现原CI的1186/683/2380/863，不把这项成功当成这些PID身份或根因证据。负例拒绝后的同进程原capture_binding节点通过，也覆盖动态scope在异常退出后未污染下一次正常捕获；M1外的其他guard仍用原严格观察路径。

PG15对普通角色隐藏其他角色会话的部分统计字段，超级用户或pg_read_all_stats可见全部统计，见[官方监控文档](https://www.postgresql.org/docs/15/monitoring-stats.html)。这解释为何owner观察可能拿到NULL，但不确定091的1186或f6的683来源。原五个M1门已经清统计快照，不能把缺刷新当根因；需要由已核控制库admin连接在原门同次按源OID读取并原样拒绝，不能在失败后另查再冒充原瞬间证据。

091的失败集合首次保留了原瞬间PID及backend_type：额外1186为字符串None，不能仅凭PID接近或M1位于dump后，就认定是自有pg_dump、维护进程或autovacuum。原sessions已先pg_stat_clear_snapshot，不能声称缺刷新是根因；不凭后续成功洗掉该次事实，也不以睡眠、重试、backend白名单或伪装appname规避精确拒绝。

07:07窄修后完整两目标通过，确认本次控制链可在原120秒协议内完成closed收尾；不能据此认定同次重复验证是此前失败的唯一原因。每阶段完整上游验证、控制文件hash、实际会话代际与双栅栏均保留，没有缓存、超时扩容或放宽成功断言。实际archive091与本轮尚待提交控制代码分开，不把当前工具提交提升为最终候选脚本证据。

2026-10-24 06:56 +08:00补一次有限本机能力核对：既有Docker PG15容器的只读exec成功，但当前PATH的command -v python3.11/python3均无结果，不能报告已有可用Core Python；这不证明整个容器所有路径不存在Python。没有SQL、安装、拉取、网络、环境恢复或重试，不扩大到WSL/代理/ACL。实际Linux应用门仍缺运行时，与已有PG15存储就绪分开。

新失败侧诊断已将未知范围缩到源backfill收尾：按当前_protocol控制流，final_live已实际观察而固定read错误仍抛出，尚余closed读取，故推断失败在该收尾读取；没有实际耗时分段记录，不能把静态重复直接认定唯一超时根因。BackfillPin.validate先完整ReplayPin.validate，随后controls又执行同一完整校验；静态展开每次ForwardInputs.validate涉及四次目标和四次源的完整候选目录核验，父ready/final均重复了这条链。

源回填首链的通用协议错误未携带可见阶段：Forward包装from None，原新fixture只在成功末段record_property，失败时未写phase或实际peer事件。首链XML无candidate属性，不能把批准起点091或fixture使用Git HEAD的设计冒称XML已实证。下一仅新fixture提前记录实际candidate，并在捕获同一SourceForwardStopped后记录有限安全phase、session_restored和至多四个实际(stage,event)；不输出PID、PG定位、原话或异常内层消息，不改变错误对象/协议/断言。未确诊，不先延长120秒或以复验绿反推根因。

05:52只读事实：隔离PG15控制库127.0.0.1:55480/core_test_main的SHOW TimeZone为Asia/Taipei，pg_settings来源configuration file、reset值相同，无相关控制角色/DB/template0覆盖。create_source新LOGIN/NOINHERIT角色及template0库不设TZ，原native_seed直用无options DSN；故其seed域继承Taipei，新观察强制UTC确有比较域不一致。此前红未记录False键，仍不能认作唯一根因。只读核实1连接/0写、不建源、不读取或输出口令/DSN。

源组合新测试的native观察强制UTC，但共用seed脚本的walk_sha256是种子会话to_jsonb整行hash，种子会话没有固定TimeZone，且角色Tokyo设置发生其后。若PG默认时区非UTC，时间戳串可能不同；目前仅为源码定位的待核假设，尚未测定默认值，不能把综合布尔红预先归因时区。需安全固定键布尔诊断和必要失败节点验证；旧9be源码及原红保留。

新core4组件的SDK必须随测试repo全部连接显式定位同一随机schema/public，否则手工造在另一个schema的checkpoint不能证明原生purge。此处不patch Saver或LangGraphRuntime，用真实DSN search_path一致；旧2/2组件不重复。

正式同一d40的push检查与PR合成checkout结果不同：push为4238/56绿，PR合成a1e1bba为4237/56加1会话拒绝。必须分别按实际checkout保留，不能把后来成功当作此前额外会话的原因或删除新诊断。

原错误码不足以区分已退出的自有客户端、维护backend或其他连接；故诊断取原实际SELECT pid/backend_type的结果，最多32项并保实际总数/截断标记，绝不把事后集合当原集合。新增字段不改变拒绝条件，也不把任一backend类型列为允许。capture-binding的新fixture改用该原集合，不再额外事后查询；原历史after_rejection_current记录保留历史含义。

源补链控制异常目标的实际同对象传播已通过，失败在新观察器只捕获InterfaceError而漏记SDK错误。根直接读取实际K3 psycopg/_connection_base.py:534–542：closed/BAD明确抛OperationalError，其他非OK状态才InterfaceError。故只修新fixture三处类型，不改生产/SDK、不把类型放宽成任意异常；原2绿不重复。回填observer的原始私有行亦按完整JSON/C顺序读取，消除未声明heap顺序依赖而不排字段。

PR #12合成候选a1e1bba的M1 prefix4目标也在pg_dump后sessions硬门拒绝，原日志只有固定错误码，没有该次实际PID/backend_type；不能用后来读取的集合或已通过的本机复验解释原失败。当前CI作业60分钟上限，实际已接近全程56分钟，新增恢复目标仍须全部执行，因此只把时限调为90分钟，不删除/跳过/弱化任何检查。

源重放worker组件的精确会话/PID代际核验可跨整个native事务及提交后purge保留同一物理lease，父在child仍活时读取完整终态；只有父核过才DONE，之后子进程只再核只读终态并关闭。真实final漂移被拒时原生撤销已提交，源保留这部分完成状态及随后测试DML，不能把协议失败误称为整链回滚。

回填精确后验不能只把四个JSON键从摘要排除：必须独立计算这些键的实际期望值，并核generated search；每个新助手的稳定ID、完整policy/血缘、operation、同事务DB时间和owner revision变化亦须逐项对账。仅第二遍全态相同仍可能把错误的第一遍认作幂等，不能替代这些首遍检查。

SourceForward首8耗时39分23秒，使用同一冻结源码与实际固定候选，没有中途改控件或重启。两个合法prefix的实际SDK历史均10→10、新版本0；setup真实调用，不能说应用了新的SDK迁移。SDK故障节点先真实设置public后关闭该自有源客户端，真实setup抛闭连错误，未假造SDK结果；另after-real-commit节点是在真实Core提交返回后的明确控制边界注入，不能称为真实网络丢包。

04:38的Linux CI run40015687408/job120627227120显示：解释器反例先被LINKED_PATH_REJECTED拦住，未触达其预期的CONTROLLER_ACTUAL_INTERPRETER；另一个capture_binding ledger节点在真实pg_dump后被INCREMENTAL_OTHER_SOURCE_SESSION拒绝，没有当时PID/backend_type证据。不能推断维护进程或竞态为已确认原因。本机两个失败节点04:48复验通过只证明此环境路径，不能据此消除Linux会话问题。

原ConnectionPool.connection和Saver均通过实例getconn/putconn取还连接；长期保留唯一物理lease可约束两条原生路径，不必替换pool/Connection类或修改业务事务。首轮前静态审阅发现两处清理优先级及prime timeout还原接缝，已窄修后才开始唯一四节点链；并无失败测试被重解释。初次连接失败、真实进程控制故障注入及非法跨thread/嵌套logical借用尚未实证，不把正常嵌套仓库事务通过等同这些负例已覆盖。

04:29 +08:00独立静态审阅：新forward/scope普通首错保留逻辑可能在清理阶段吞掉后来的KeyboardInterrupt/SystemExit/GeneratorExit；SDK setup后也应再次核实际Saver/SQL再允许grant。两项尚未修复，首8原样在途不得改变绑定代码；追加两个独立真实PG故障节点先写静态，原SDK/PG结果及业务门不替身。初始代码的源码集合、候选与失败记录以后分别保留，不靠重跑全部绿项掩盖修正。

source_postcheck首链为`private/safe-narrow-b249cd4b0fed424bb51981251918c464/metadata.json`，03:56:21–03:58:14 +08:00，6 passed/1 failed in112.07s。唯一失败是新测试试图把core_entities.status从text改成varchar(64)，PG原生FeatureNotSupported拒绝，因为既有core_embedding_retirement触发器依赖该列；尚未调用被测postcheck，独立nullability分支也未执行。根只批准将类型故障改为实际有行且无此触发依赖的core_subjects.label，先实读行数/最大长度作夹具前置断言，保留updated_at DROP/SET NOT NULL及全部拒绝/不修复断言。仅该失败节点复验为`private/safe-narrow-ce8b391fc7604fb0a290320aed84d74a/metadata.json`，04:00:10–04:00:29 +08:00，1 passed in18.42s；旧6绿未重跑。两轮均实际K3 host、Asia/Tokyo、清凭据/关追踪，真实模型/外发/服务器0。首链同JUnit的两个prefix正例均记录sdk_checkpoint_versions_before=10、after=10、new_migration_versions=0：真实setup已调用，不能把新增0版本写成setup未执行或零SQL。

Source guard首链为`private/safe-narrow-6e1df593540c458bb46f205f00efc683/metadata.json`，03:35:54–03:39:11 +08:00，2 passed/6 failed in196.04s。纯文件existing-only及control漂移先通过；其余六项在whole BackupInputs比较即拒绝，未触达各自目标。旧测试repin手工构造的ReleasePin.locks沿LOCKS常量顺序，官方parse按键排序；只有新测试自有fixture在任何M1捕获之前通过官方BackupInputs.parse(source_document(...),workspace)规范化，生产whole-object比较没有放宽。

仅失败六项复验为`private/safe-narrow-525e369381714451b8dcc8862856dc38/metadata.json`，03:40:38–03:43:32 +08:00，3 passed/3 failed in173.07s。真实缺fence、缺marker及backup-started额外字段三项已按预期拒绝且未补文件；4/7正例及同字节marker换inode共同在锁内复读fence时收到SOURCE_GUARD_MATERIAL_FAILED。获批真实纯文件诊断确认：Windows原LockFileEx独占锁内，空fence与9字节合成fence的新句柄read_bytes均抛PermissionError（winerror=None）。这是新guard的实际跨平台接缝，不能归为夹具或省略fence hash。

最小修复后仅三红与受影响纯文件节点复验，`private/safe-narrow-70822d1398fc4da29a93b9704a307fa1/metadata.json`，03:51:05–03:53:40 +08:00，4 passed in154.09s。真实Windows锁内原句柄可读、新句柄拒绝，默认file_lock仍yield None；4/7源实际持文件/PG双独占锁、仅四个自身实际PID连接且都以只读启动，同字节marker换inode退出时拒绝。最后四个此前未执行节点单独为`private/safe-narrow-ce24164f06024dacb4695dd51eb2eb95/metadata.json`，03:54:05–03:56:20 +08:00，4 passed in133.93s：真实timestamp字段漂移、queued run、额外当前PID及额外view均拒绝且不修回/清理源。上述各轮与原始失败日志分别保留，未重复其余绿项；均清凭据关追踪、TZ Asia/Tokyo、真实模型/外发/服务器0。

controller已加载业务模块，不具备fresh worker的-I/-B进程条件。因此新增独立运行时门，核当前解释器、venv内实际distribution与依赖边、PostgresSaver实际模块及MIGRATIONS；不借worker的旧回执宣称controller已验证。四个新目标使用合成候选/manifest绑定及真实审核锁副本，实际解释器/已加载模块参与核验；没有验证真实Git发布包或PG接线。

当前候选export_withdrawals所读owners/revocations/tarot_requests/mutation_requests/outbox及列均存在于prefix4。导出阶段只能先核连续历史后直接调用真实候选导出，不调用要求完整8的repo.verify_schema或initialize。恢复144回执还不是“备份时源库全状态==恢复后升级前原始状态”的证明，这一接缝后续由恢复owner实现，不能用任意JSON放行源库升级。

实际PG15验证：worker在只读RR事务内先IMPORT父snapshot，再查询PID握手，候选原生export内嵌同值SET RR/RO正常工作。测试在snapshot导出后由不合作连接写入新撤销并推进sequence：真实候选旁账与真实pg_dump均看不到新撤销；新快照检查实际看到源变化并拒绝完成，保留dump/旁账/维护标记。序列也独立检测，未假称受MVCC保护。

M3a首链两正例的旧字段比较错误来自将schema_migrations新增5–8行当作原行漂移。该断言原保护“全部旧行/旧字段含时间戳不变”；根审允许前后仅在这张账本表按version<=原prefix取旧行，完整1–8checksum核验仍独立保留，其他表不排字段、不排旧行。实现和受pin SQL未因该夹具问题改动。

## Decision Log

2026-10-24 08:16 +08:00：TargetProof 的失败发生在 consume 首个最终核查，mint 与测试内两个 with 连接均已返回；这些事实不足定位额外会话或实际忙run。新 M1 observer 只绑定源库/备份动态作用域，不能借它诊断恢复目标。最小诊断只在原目标 SELECT 同时读取忙run计数及该库 pid/backend_type 集合，拒绝对象附限32条的安全摘要及 Python 异常 note；无query、application_name、DSN、正文。总数与截断位保留，异常本身仍抛原码，不追加失败后再读或删数据。原目标控件已纳入既有 hash pin，新调用须重新审 pin；发布与全局停写仍 No-Go。

2026-10-24 07:49 +08:00：根审要求observer每次重核owner当前只读、admin只读/autocommit及真实全统计可见权限，新增查询显式限定pg_catalog；绑定对象仅保控制库身份四字段，不再持有password。新负例收紧到精确两个client backend，防另一未知会话替代所要证明的拒绝原因；原成功与失败正文不删改。控制helper120行、最长函数33；新测试59行、最长44，既有incremental_pg449行只窄改、最长56，维持旧文件软目标例外。Ruff E/F/I/B/UP/SIM、120列format及AST/diff均通过。

2026-10-24 07:42 +08:00：在独立v4/p3-wire-session-visibility-20261024（07dbf97子分支）实施M1限定typed observer。保sessions二参与candidate_export四参；backup原已核admin只读/autocommit控制库连接存活至capture结束，绑定实际owner连接对象/PID、源database_oid和admin身份，同次按datid读实际行集供原精确集合比较及七字段有限诊断。离开M1动态作用域后其他guard保持原行为。连接/身份/统计权限/NULL类型异常失败关闭，不grant、不按类型放行、不睡眠重试。新helper只懒加载，防不可变旧候选runpy snapshot时借用新依赖；加入CONTROL_NAMES哈希闭包（8→9），旧8控pin继续拒绝而不补写。只新增真实异角色会话仍拒且类型可见的必要负例，并复验原f6失败capture_binding目标；先静态冻结根审，再授单测试槽。主线承担本片控制路径，未触碰模块记忆或暂停线。

2026-10-24 07:14 +08:00：保留091本次setup错误及未执行检查，07新CI运行时不重复触发、不改M1控制文件。不掌握1186身份便不放宽会话门，按用户“阻塞写后切可做项”转向既有累计预算方案；无需新的用户决定才能继续离线开发。

2026-10-24 06:48 +08:00：根完整审阅115行BackfillPin去重实现，公开controls仍全核、validate保一次完整上游及当前全部自身文件/ledger/SHA/绑定核验，函数最长45。因实际改动了validate的控制集合计算路径，除原红整链外，需再验证同文件既有默认/坏pin零副作用节点作为受影响安全边界；这是新代码的必要验证，不是稳定性重复，原其余绿项不重跑。仍保持091实际候选归档、成功断言及120秒，首链和诊断红分别保留，原重复是否为唯一原因仍未知。

2026-10-24 06:47 +08:00：只在新first_release_source_backfill_pin.py拆出私有controls组装helper；公开controls仍先完整replay.validate，validate自身仍先完整replay.validate，再用私有helper核当前DIRECT hash/继承冲突并核全部controls、ledger、binding。没有validated布尔或持久cache，不跨协议边界复用结果；ready、final、进程结束后仍逐次完整pin.validate及_active真实PG/锁/维护材料。原候选091、协议120秒和全部成功断言不变；这是去同次冗余的最小修正，不先宣称收尾已修，根审静态后仅跑原红。

2026-10-24 06:29 +08:00：首链红记录完整保留，原负例不复跑。唯一下一步是新fixture失败侧安全可观察性，收集原异常已有phase和实际已观察peer事件后原样raise；不再读本机PG/进程找稳定性，不改候选/生产/超时。若唯一红复验仍红，再按实际阶段切换可做项，不能连续盲重试。

2026-10-24 06:24 +08:00：独立只读审阅确认正式CLI、应用停写与中央保全是三个独立剩余项：当前incremental CLI只备份，Forward仍local_drill内部API；repo.transaction未取writer_fence合作共享锁，工具独占锁不能证明全部应用已停写；现中央后验仅新四表空/sequence未用，没有历史prefix8账本保全。暂不增加一个只有validate的重复CLI来冒进度，先辨明全部写入口与受信配置接点；实施前另写最小方案及真实验证，不触动在途回填控件。

2026-10-24 06:08 +08:00：source_backfill_pin默认None不改变已有路径；显式提供必须同时有已验证SourceReplayPin，缺任何绑定首I/O前拒绝。真实source_backfill只在原creator/双锁/活witness且privacy replay完成之后调用，成功后仅解除backfill_pending；原生源升级、正式恢复/runtime/Linux、中央身份、全局停写和publication位继续false。新两目标不重跑旧源replay或组件绿项。

2026-10-24 06:05 +08:00：原红复验绿后冻结源replay接线与292行专属测试待提交；不把UTC输入规范化后的13项全true写成原红唯一False已知。新backfill三模块与318行整链测试仍未接线/测试，本次不与已验片一同提交；后续必须另接并跑真实组合。

2026-10-24 05:53 +08:00：仅批准新chain fixture的实际原生seed/correct/blob使用明确UTC DSN proxy，原source环境不改、之后captured的Tokyo角色变化保留；先以同DSN真实SHOW核UTC。原完整walk hash、隐私与保留不变量不降，原NATIVE及旧测试不改。新综合观察仅加固定bool诊断，随后只复验原红；默认已绿不重复，不改生产/时限。新backfill整链复用这一唯一规范化新fixture而不再复制无TZ旧种子；尚未接线/测试。

2026-10-24 05:51 +08:00：组合首链红后先只读核实际合成PG默认TimeZone及seed/观察域，不重跑绿节点、不动生产。允许后续新测试加入固定键bool诊断/JUnit，不能记录原话/ID/DSN或删掉walk完整行不变等断言；具体修正须待事实依据，未授权盲重试。

2026-10-24 05:46 +08:00：回填新worker仅用当前owner外层repo.transaction，effects同owner嵌套复用该原连接/事务；COMMIT返回后才owner_verified，失败保owner_started和前序已提交状态。effects/expected必须同candidate manifest且SHA等于审核控制pin，缺候选helper拒绝；不从控制树补业务。三文件仅静态，不以审阅代替真实PG/进程验证。

2026-10-24 05:38 +08:00：回填core4/撤销后仅新增两行为专属测试，原生结构结果来自ThreadIngress/AgentRuntime/ScriptedPort，缺助手历史只精确删除其实际native消息作合成gap。撤销先实际retire_fact再原export/apply，privacy提交后purge不外套事务，随后才回填；全部业务结果及原SDK保持真实，不为新测试改生产。

2026-10-24 05:34 +08:00：已验证9be44b9推送后另开接线子分支，保父CI运行；Forward仅增加精确可选pin的首I/O前校验和活witness作用域内调用。旧None默认不导入新进程模块，回填及正式发布位仍false。两个新组合行为由独立新测试承载，旧8/4/2绿不重复。

2026-10-24 05:26 +08:00：M1原函数只扩实际同一次查询列并附error.session_diagnostic，不含query/appname/DSN/正文，str固定码及精确PID集合保持。两个测试模块仅在拒绝时打印该有限字段；打印普通失败仍抛原拒绝，进程控制不吞。M1pg437行、原共享测试472行局部延续既有400软目标例外（均<600，函数56/47），不为少量诊断另拆会影响旧pin/import的helper；capture测试300行/函数60。CI YAML已解析且仅timeout改90，无测试步骤移除。

2026-10-24 05:20 +08:00：允许新SDK故障fixture仅将实际cursor捕获与SDK/restore类型断言对齐真实OperationalError；保原真实setup栈、同interrupt对象、清理错误、Core8/原行/marker与registry断言。根先完成会话失败诊断控件后冻结，再仅补该1红。回填首链前的唯一次静态更正是私有rows确定排序，没有用after结果构造expected或删掉允许列来凑绿。

2026-10-24 05:18 +08:00：待R3源控件补链结束后，拟只给原sessions失败附加同一次实际查询的有界PID/backend_type安全诊断，保留原精确集合条件、固定str错误码与立即拒绝，不额外等待、重试或关闭连接。原M1测试及capture-binding测试只在拒绝时输出该安全诊断；新增断言必须验证真实额外客户端属于原失败集合。仅复验CI失败prefix4目标及受影响实际额外会话负例，原大套件不重跑；SourceForward在途控件现在仍不动。CI时限90分钟为检查增长留余量，不能当作会话失败已修复。

2026-10-24 05:10 +08:00：只冻结五个新源重放组件文件；首链前根审补了首写前ready状态绑定、实际final状态/活lease握手及首个进程控制异常优先。四个组件不伪造SourceWitness、不跳过原实际候选函数/PG；不新增普通成功JSON放行入口。下一同call可选pin接线须等Forward补链停下后再单独实施/验证，当前不改在途代码。

2026-10-24 05:06 +08:00：新增first_release_backfill_expected.py及first_release_backfill_effects.py独立DI组件，未来受pin候选worker只传实际核过的MemoryService/backfill及只读解析函数。先不改冻结的进程、Forward或业务。先做真实core3历史正例和后半真实写入后异常整事务回滚两个组件行为，core4与撤销后不复活的后续两个行为另待。调用backfill原生owner事务；只包回填preview/apply/second，不外包已提交privacy/purge。

2026-10-24 04:55 +08:00：原SourceForward首8完整结束后，才允许改新forward/scope中的两处已审缺口：清理阶段进程控制异常优先同对象传播；实际setup后再次verified_saver核当前类/SQL并取得核后数量，再进入checkpoint_completed/grant。先静态审阅，再只测两个新增故障行为及一个必要受影响prefix7正例，原首8其余绿项不重复。原冻结源码、候选与日志按其自身证据保留。

2026-10-24 04:49 +08:00：只将测试自有sys._base_executable反例路径.resolve，保留生产符号链接拒绝与精确解释器不符断言。capture fixture仍先执行原sessions精确门，只有固定拒绝后才读当前pid/backend_type/allowed集合；标记after_rejection_current，不记录query/appname/DSN/正文，不重试、等待、关闭会话或放宽允许集合，诊断普通失败仍保留原拒绝。SourceForward在途三控件未改，首8结果不能挪用此新头。

2026-10-24 04:36 +08:00：只新增first_release_source_pool.py及专属PG测试，原计划统一记证据；不改业务、已有tools或SourceForward首8冻结控件。有限gate异常用BaseException以逃过候选普通Exception兜底，真实进程控制保持原对象且优先，已有gate poison随后，普通业务首错优先于普通清理错。初次原getconn前只临时设该全新min0/max1池reconnect_timeout=0，退出关闭后还原；初次失败没有实证，回执明确initial_connect_failure_tested=false。没有source worker/父子ACK协议或源写权限，SID与实际审核pin须由后续协议提供。

source_postcheck仅新增`tools/first_release_source_postcheck.py`及专属PG测试，不修改旧ACL、RestoreContract、业务/迁移/SDK或源写入口。真实autocommit连接必须在RO/RR、pg_catalog事务中，当前源DB/role OID由checked_identity核，SID仍由未来scope的受审admin连接核，owner不提权。原字段按capture列集合、UTC与PG jsonb_agg/C排序摘要比较；仅对Core账本取原prefix、checkpoint账本取前态实际版本集合，完整新history与SDKhistory另核。只有新fixture的类型故障换列，未删/停retirement trigger、未降低旧字段或列元数据断言；测试中对夹具故障的恢复发生在拒绝后状态不变已实查之后，不是helper自动修复。根于复验期间从88f1d27切本地子分支`v4/p3-wire-source-forward-20261024`继续，父远端`v4/p3-wire-incremental-20261024`保留88的CI；未reset/stage本片，复验archive使用明确HEAD。新终态观察不是SourceUpgradeWitness，JSON不赋源写权，guard/runtime/proof组合及M3b继续待做。

Source guard只新增`tools/first_release_incremental_guard.py`与专属PG测试，并获批窄改原writer_fence的existing_only/return_handle参数。默认锁行为不变；existing_only不建目录或重建缺失fence，return_handle仅供guard内部用实际持锁句柄读取，held_source始终yield None、不暴露连接/句柄或写权。每次fence读取前后完整核pathstat/fstat的dev、inode、size、mtime、字节长度与SHA，marker/start仍独立读取并核严格原形状、身份/hash；不跳过Windows真实锁。新guard三个实际控制SHA与原M1八控制、CaptureBinding四控制分别完整验证，实际SID/OID、合法4/7角色/关系权限、owner全集、真实活动PID与无busy源、完整UTC列/全部行字段/raw sequence均重核。持双锁后可在body内生成目标证明，但当前只读scope退出仍要求原capture不变，不能包装DDL或凭返回JSON获得源写权限。未来源编排须另消费sealed TargetProof与实际controller RuntimeWitness并在表锁后取fresh snapshot；现片不提供该能力，也不宣称全局静默、零一切FS动作或Linux通过。

controller运行时凭据只作为未来同call源升级的必要条件。私有registry登记RuntimeWitness，verified_saver消费时重新核全部活动输入并返回同一个已验Saver类；复制的JSON摘要不赋权。后续必须与单次TargetProof共同形成源升级许可，任一单独通过都不能迁移源库。运行时门不访问PG、模型或网络，不声称wheel/.pth供应链、Linux或正式发布通过。

主线裁定M1只证明阶段前/后精确无额外会话，不做脆弱OS/TCP PID追踪，不按application_name放行，也不声称dump期间全局排除连接。回执global_quiescence_verified=false、session_checks=before_after。父owner只读REPEATABLE READ事务导出snapshot并保持存活，实际pg_dump --snapshot和候选worker在业务读前IMPORT同一snapshot；阶段后另开新快照比较当前源数据，漂移则失败保留。sequence不受MVCC保护，单独前后核last_value/log_cnt/is_called；未来跨恢复对照只按last_value/is_called作语义比较，log_cnt原证据保留用于同库漂移，不能删除或伪造一致。

本片仅新增四个tool、一个PG测试与本计划。新输入绑定候选/manifest/三锁、程序与解释器、新worker及被复用控制worker真实hash、实际系统/数据库/角色OID及owner全集。文件/PG锁以实际库稳定身份绑定，固定先文件后PG；维护标记和部分输出在失败后保留，既有输出或已进入的operation不自动接管/重试。不会修改角色LOGIN/权限、杀会话或停服务。

公开成功回执仅为backup_captured。正常工具链实际连接为admin控制库只读身份盘点1、writer只读身份1、owner锁与snapshot1、候选只读worker1、pg_dump1，共5个；admin连接不读pg_authid，阶段结束即关闭，不作为额外源会话豁免。测试额外创建/恢复的观察库只证明导出行为，不自动放行源库升级。外部审核pin是可信输入前提，不认证审核者，也不证明wheel/.pth或Linux供应链。

根审授权测试文件445行的局部软目标例外（硬上限600、函数最长47行）：保持“同一真实child实际写入→真实backup→marker拒绝第二写”协议证明集中，不为这一个新增目标另造测试support。业务tool未改，原8项不重跑；新增目标必须单列证据，不称一次9/9。

## Plan of Work

first_release_incremental负责不可变输入与CLI；first_release_incremental_pg核实际PG身份、其他会话/active/lease、源完整表/sequence摘要并执行受pin pg_dump；first_release_writer_fence提供Windows LockFileEx/POSIX flock及PG锁的合作协议；first_release_incremental_worker以纯stdlib bootstrap加载已核控制基础，固定实际候选导入后只读导出。prefix4/7源数据只读，不新增迁移或依赖。

## Concrete Steps

在release-prep运行显式pin的first_release_incremental默认校验应无连接/进程/文件写；加--backup-local才取双栅栏并写该operation私有目录。PG与文件独占锁须真实跨进程互斥，不按application_name识别可信会话。只读worker在IMPORT SNAPSHOT后才握手回报实际PG PID，由controller精确允许；pg_dump没有可信backend握手，不假造关联，只在其前后核没有额外源会话。前后检查不是dump期间全局静默证明。

## Validation and Acceptance

沿用F01–F04、X03“不复活、不重发、owner隔离”约束：实际prefix4/7已有库生成可由PG15读取的custom dump和真实候选非空旁账，源全部字段/时间戳/sequence摘要不变。错误OID、活跃run/lease、其他会话、文件或PG锁冲突停止；不修改源行或修权限。默认与缺显式授权入口必须零副作用。首链≤8必要组；本机Windows结果不算Linux。

## Idempotence and Recovery

失败保留维护标记、已写输出和实际阶段，不删除、自动重试或清理。OS/PG锁随进程退出释放，不等于解除维护；参与协议的writer仍须检查标记。本片没有清除维护或恢复旧目标的命令，没有源库迁移/回退动作。

## M2 seam（本机定向实测完成）

M1已由根审提交8be4920effcdd1bb3aac52fda7d6dcdab766dfb7。本片新增`tools/first_release_capture_binding.py`与`tests/v4/release/test_first_release_capture_binding_pg.py`，仅小接`tools/first_release_local_restore.py`的显式模式/参数及verify_original之后、_upgrade_new_target之前调用；本计划继续独占，恢复effects及原恢复计划不改。默认无binding仍保持既有行为；没有接受任意既有库或单DSN的入口。

独立不可变CaptureBindingPin绑定M1原输入、backup-receipt、源完整状态、dump、ledger的实际SHA，以及candidate/manifest、目标operation和受审新helper/接线控制代码SHA，不设置admissible布尔。原M1输入继续精确绑定cluster系统号、数据库/角色OID、owner集合、prefix4或7、实际Python/pg_dump、三锁与全部8个控制hash。所有材料限制同workspace下各自固定operation目录，新fr_restore必须与源fr_upgrade身份不同。审核pin为外部信任输入，不认证审核者；不能把某JSON中backup_captured=true当事实证明。

调用前只读核所有不可变文件与完整M1 before=after、canonical state哈希，source/dump/ledger/candidate/manifest/prefix逐一绑定。实际比较函数只能在同call仍持creator锁的新目标内执行：先_require_creator，再只读RR/pg_catalog确认实际新库身份、owner全集、原prefix及关系集合；表全部原字段摘要必须精确相同，包括时间戳和checkpoint，sequence集合与last_value/is_called相同。源last_value/log_cnt/is_called原证据完整保留；log_cnt不拿来要求跨pg_restore相同，也不重写成相同。任何缺表、额外关系、字段/sequence漂移或pin不符均失败保留且不进入升级。

通过仅给嵌套local_capture_binding_verified/local_original_content_verified；source_restore_content_verified、native/runtime/Linux/central/publication等正式位仍false。随后才调用现有新目标升级函数，本片不前向fr_upgrade源库。已用真实M1完整候选捕获和实际pg_restore核prefix4/7，另以真实目标字段/sequence漂移、hash/身份错配、缺same-call负例证明失败仍停原prefix；逐轮实际结果如下。

根批准M2实施并额外最小修改`first_release_incremental_pg.py`：新增显式`postgres-jsonb-utc-v1`投影，实际事务内SET LOCAL TimeZone=UTC并确认事务生效；完整表行字段（包括时间戳）不排除。snapshot新增columns map，按实际非dropped用户列attnum顺序记录字段名、format_type、attnotnull，不绑定物理attnum/OID。此map纳入新before/after与源state SHA，M2逐表精确比较；旧无投影/columns证据硬拒，旧8/8+1/1捕获hash不重解释。默认值/约束/所有DDL与供应链认证不是这个列集合核验的范围。M1 pg可局部超过400软目标，硬<600、函数≤60，不拆未pin helper。首链≤8新行为，实际新捕获验证源/目标不同时区、空表列漂移，不重跑M1旧9项。

新UTC捕获另含body-free capture_lineage，来自本次已实际核验的inputs：operation、manifest/三锁、SourcePin实际系统/库/角色OID与owner/prefix、runtime两程序SHA、8个controller SHA。M2将其与原M1输入逐字段比较，再校受审receipt哈希；不接受receipt自报替代外部pin。首链使用当前已提交416d884的完整候选包，所有M1捕获均新生成，不补造8be之前的旧证据。代码已静态冻结：新capture_binding、local_restore显式接线、新UTC的M1_pg、新真实PG测试及本计划；R3恢复effects和旧Plan不在本片。

首链实际3通过/5失败：`private/safe-narrow-439dd6fb00e846c18c7476f2b5aae7b1`（02:21:39–02:25:44 +08:00，243.97秒）。五个PG比较目标共同在新代码读取creator.info.dsn时失败：psycopg该属性会解析隐式默认passfile并调用Path.home，稀疏测试环境无USERPROFILE。实现改为原调用链显式传入已经严格验证的dsns给_require_creator和owner只读连接，不重建隐式DSN、不加环境或改测试断言；仅允许重跑这五个失败目标，原三绿不重复。

五个失败目标重跑为3通过/2正例失败，`private/safe-narrow-8ee83a0682d04e91b96b566fd8ca4186`（02:26:49–02:29:36 +08:00，166.50秒）。三个实际字段/空表列/sequence漂移负例都按预期在升级前受控拒绝；两个正例已过内容绑定，后续既有升级ACL因M1复用夹具额外的synthetic_backup_seq而拒绝（合法profile只收0008 quota seq）。保留该ACL行为，不删恢复后的seq、不迁就实现放宽断言。仅将这两个正例显式参数化core-only源，在本次新捕获之前去除纯测试附加seq，使实际prefix4/7源符合升级profile；带seq的漂移负例保持原样。随后只重跑两个失败正例，已有六个绿目标不重复。

两个合法profile正例单独复验2/2通过，`private/safe-narrow-7ff0903d655c47da88c8b38a1977d406`（02:31:28–02:32:42 +08:00，72.26秒）。源owner实际默认Asia/Tokyo，新目标owner实际默认America/New_York，源与目标不同DB/角色；新UTC原始内容/逻辑列集合匹配后，同call前向4/7→8及既有精确ACL通过，恢复阶段连接8。原3+后3+最后2组成八个行为的证据，不冒称一次8/8；旧M1九项未重跑。只读比较失败的三个真实PG反例确认目标仍原prefix、没有0008中央关系，且没有自动重试/清理。

最终本片五路径为`tools/first_release_capture_binding.py`、`tools/first_release_local_restore.py`、`tools/first_release_incremental_pg.py`、`tests/v4/release/test_first_release_capture_binding_pg.py`与本计划。三个tool及新测试分别301/258/421/279行，函数最长60行，Ruff E/F/I/B/UP/SIM及120列format通过；M1_pg为获批局部软目标例外，硬<600。capture pin绑定四个consumer控制hash及M1八控制/runtime/source lineage；所有字节hash在实际比较前后重核，未认证审核人、文件模式或完整运行时供应链。

## M3 design（获批分片实施，尚未接入源升级）

M2已审并随9c46ba5/206f43f推送。下一入口仍只接受已存在的本机fr_upgrade合成源、合法连续prefix4或7和精确系统/数据库/角色OID，默认0连接/0进程/0文件写；显式local apply才能进入。源prefix8、任何中央四表/usage sequence历史、额外关系、活动run/lease/额外会话都硬拒，不能provision/重置账户或假借旧b9/freeze/install/publish。

建议M3a新增`tools/first_release_incremental_upgrade.py`（入口/同call编排）、`tools/first_release_incremental_guard.py`（typed源身份/维护/fence/完整状态门）、`tools/first_release_migration_steps.py`（中性SQL/历史/迁移/checkpoint/grant原语）与`tests/v4/release/test_first_release_incremental_upgrade_pg.py`。只小改`first_release_local_upgrade.py`委托中性原语，保留原_require_creator及fresh-target专用门；`first_release_acl.py`抽出接受真实已验证连接/窄数据库身份的内部检查，旧RestoreContract.dsns入口不放宽。`first_release_local_restore.py`内部成功分支可产仅内存mint的TargetProof，public JSON保持兼容，避免将可编辑success.json变成源库写权限。必要源输入拆分另报，不借行数藏未pin helper。

先消费同一受审新UTC M1原pin/receipt/dump/ledger及M2/CandidateReplay pins；同次实际创建另一个新fr_restore，完成M2原始比较→前向8→原生双重放/擦除/中央不变→精确ACL。只有这条真实调用成功，内部SourceUpgradeWitness才能绑定source OIDs、实际新target OID、candidate/manifest/三锁、capture/replay全部哈希及同call来源；没有导入旧restore回执或用户JSON true的入口。R3本轮负责该已有组合的单链集成样本，本代理不改其新测试或恢复effects/原恢复计划。

源按稳定身份取得file→PG独占锁并核原M1持久维护marker，证明期间继续持锁；admin/writer身份连接只接受自身实际PID且关闭后不豁免。源owner只读RR前检，且紧邻首次DDL再以新快照同UTC/columns/完整原字段/原sequence原值（含log_cnt）精确等于捕获点；有漂移即止。M1通用备份可观察附加sequence，但M3只收合法Core4/7升级profile，不能为附加测试seq放宽ACL。初始writer必须符合该前缀的DML/迁移账本只读/checkpoint/无DDL、TEMP、继承/owner权矩阵；缺权或越权拒绝，不靠授旧表额外权限修成合格。

中性apply_core保留原Migrator完整事务、schema advisory锁、候选受pin SQL与精确前缀hash核验。源DDL事务必须显式READ COMMITTED，按稳定顺序NOWAIT锁全部已存在业务/检查点表后才取新快照并核完整源状态，避免预先identity/锁查询在RR下固定旧快照；精确相等后才在同一事务前向1–8。Core提交后按旧columns map逐一核原字段与sequence，新增关系单列核空；checkpoint/grant末次再取新快照核history8、会话/busy、数据/sequence，不能复用只接prefix4/7的source_scope。checkpoint迁移因concurrent index必须另一个autocommit阶段，控制器真实Python/活动Core依赖须先核验，不能仅凭锁文件相同使用未验PostgresSaver。随后最小新增授权事务和真实owner/writer精确ACL、中央仍全空核验。全量grant原语只在源旧profile已精确合格时重授新表；缺权或越权先拒绝，不能称修旧权限。

新`first_release_source_profile.py`按前缀分别核关系/权限/实际PG身份：prefix4不得存在业务routine/非内部trigger；prefix7必须恰有已审clear_retired_embeddings函数及实际挂在core_entities的AFTER ROW UPDATE OF status/data、enabled触发器，不只比函数hash。源owner/writer都核真实库/角色OID、PG15本机端口、NOINHERIT及非高权/无成员关系、pg_catalog目录；writer逐表/列精确DML或迁移账本只读，并保留PUBLIC数据库任何授权、公共schema CREATE、TEMP/DDL/owner权拒绝。未知关系/sequence/视图/规则或可执行SECURITY DEFINER都关闭，不自动删除。

same-call TargetProof须用私有内存seal/registry单次消费，不能由公开dataclass构造或JSON重建。仅在new_target creator锁内部，真实M2原始内容绑定→8→候选原生重放→重放后的末次实际ACL/中央四空表与未使用seq核验全部结束后mint；现旧_upgrade_new_target的ACL发生在重放之前，不能代替末次核验。所有新helper和后续ACL/local_restore/typed producer修改均须进入同一审核pin传递，缺一关闭。此证明尚未编码，本片不因两个内部helper存在而开放源升级。

03:05第一静态小片为`tools/first_release_migration_steps.py`与`tools/first_release_source_profile.py`：前者读取完整受审candidate的1–8 SQL，连续原prefix/hash与数据库owner核验后保持单Core事务；后者只读证明合法4/7源的真实关系/权限/触发器。两个文件尚未被旧入口导入，不修改共享旧tool，也不触碰R3在途M1+M2+replay集成样本。根尚未授测试令牌，当前仅Ruff/AST静态检查，不宣称PG行为通过。后续拟首链≤8必要组：合法4/7、改触发器挂载、PUBLIC/缺权/越权、未知关系/可执行definer、真实SQL前向及事务失败不部分提交，具体节点待根确认分片。

03:10第一基础片实证范围为8个真实节点：合法prefix4/7逐一核owner/writer精确profile并实际forward8，旧列映射内全部原字段/旧行（账本仅旧prefix）相等，完整新history精确1–8；实际错误trigger列与disabled、PUBLIC DB CONNECT与schema CREATE、writer缺DELETE与迁移账本INSERT、额外view与可执行SECURITY DEFINER分别成对验证受控拒绝（仍只计4个节点）；实际错误数据库OID不写；合法prefix4历史消息at_ms非法使0005实际DDL成功后0006索引::bigint实际返回PG22P02，整Core事务回滚至4、完整snapshot及原列不变，runtime列/新run_steps不存在。未修改受审迁移、源码包或原6绿节点断言。

首链`private/safe-narrow-619a51e3d08e4fbaa6ddc1942a6a9b05`，03:06:56–03:08:25 +08:00，6 passed/2 failed in87.68s；两失败均FORWARD_CHANGED_ORIGINAL_FIELDS，原因如上。仅两个失败正例复验为`private/safe-narrow-51d8785c4426414daa6ad3e22cb50b3e`，03:09:43–03:10:15 +08:00，2 passed in31.64s。证据为6+2，不称单次8/8或全部M3完成；测试时区Asia/Tokyo，真实模型/外发/服务器均0。本片尚未接入source adoption、维护/fence/完整capture门或typed TargetProof，没有源升级命令；真正源guard仍需核实际cluster系统号、同call新恢复证明和已验运行时，不由这两个内部helper的dict回执赋予写权限。

这些阶段不是一个原子事务：Core SQL失败可整段回滚；Core提交后checkpoint/grant/后验失败会留下Core8及可能部分checkpoint，必须记录真实phase、保留新目标/备份/marker/所有对象，不自动回滚、重试、清理或一般prefix8接管。源会话例外只来自实际自建连接PID/worker握手，不按application_name。当前应用尚未参与合作fence，checkpoint等非原子间隙不证明全局停写；各阶段前后核session/state并保持global_quiescence_verified=false，正式native/Linux/中央身份/发布继续No-Go，最后也不解除marker或开writer。

M3b再新增`tools/first_release_incremental_backfill.py`、`tools/first_release_incremental_backfill_worker.py`与独立PG测试。实际签名是候选`mingjing_core.memory.backfill.backfill(MemoryService(repo), owner, apply=False/True)`；不能使用只加sys.path的旧B1 worker或控制树业务替代候选。新worker复用受hash pin的纯stdlib来源/真实Python3.11活动锁检查，另设严格fr_upgrade/OID门，不放宽原replay_worker.target。握手真实PG PID后才由parent认可；preview→apply→第二apply在原生owner锁与外层回填事务内完成，dry全状态不变，second三个写计数为0；现存原始行只忽略允许的search_tokens/thread_id/at_ms/origin_conversation_id元数据，其余字段/版本/正文/时间戳保留，新增助手行必须真实来源且稳定ID。样例ID仅hash，中央四表/seq、非回填行、检查点与投递不被触碰。失败只回滚该未提交回填事务，不能声称撤销已提交的前向DDL。

根已裁定M3b必需范围：backfill_entities仍遍历active fact，只在新目标重放不能证明源回填隐私安全。源8上必须先按同一实际候选落实既有撤销/收据双重放及独立擦除后验，再开始backfill，保持native apply自身事务和提交后checkpoint purge边界，绝不外套大事务。它是用户已授权开发内落实既有撤销，不发起新删除；可独立成片。M3a若只做到DDL/ACL，必须明确backfill/源隐私闭环未完成、保持closed，不能跳过此点宣称首发就绪。

## M3a same-call TargetProof（03:18获批实现前计划）

本片只新增`tools/first_release_target_proof.py`与一份专用PG测试，窄改`first_release_local_pg.py`及`first_release_local_restore.py`，不接source driver/guard/backfill。公共execute默认仍返回既有JSON，默认校验零连接/进程/文件写；旧_require_creator签名与fresh-target门不改。local_restore内部抽`_applied_target` contextmanager复用真实restore/M2/upgrade/replay过程，public execute在context内取JSON；私有`_proved_target(inputs, apply_local=True, upgrade_local=True, capture_binding=..., withdrawals_replay=..., target_proof_pin=..., environment=...)`必须全显式，不能拿旧execute回执追认。

local_pg.create_target在本次创建两roles的事务内立即读取并保留两个实际OID，CREATE DATABASE成功后立即读取数据库OID/datdba，在public初始化之前建立私有生命周期记录。registry用id(creator)键且record强持creator实例，并核record.creator is creator，绑定operation/database、三OID及backend PID；new_target的finally总撤销进程记录，不删除任何PG对象。仍yield原Connection；私有`_birth_identity(inputs,creator)`只读取此活registry，不从JSON或当前同名库重新认定出生身份。proof producer与consume必须把当前实际OID逐项与出生记录比对；未注册、已关闭/离开context、同名库/角色替换均拒绝。

新TargetProofPin是独立外部审核可信输入，固定canonical输入绑定SHA与实际producer/helper控制路径SHA；绑定LocalInputs（候选/manifest/三锁、原prefix/dump/pg_restore及路径）、CaptureBinding/M1源身份与实际捕获/旁账字节、CandidateReplay候选解释器/worker/effects/ledger。依赖旧generic grant函数时也绑定实际被调用的控制代码，不借其旧B1 admission/固定候选；candidate apply/export仍在已验fresh process执行。它不认证审核人、文件保护模式或完整wheel/.pth供应链，不把输入JSON里的true作为放行依据。

本片目标证明只说明该次本机恢复/候选重放/最终数据库核验，controller运行时仍不标已核。现worker.runtime同时要求-I/-B等fresh-process条件，不能直接移植到已加载业务模块的controller并冒称通过；后续source升级入口须在实际受审候选解释器启动的控制进程里，独立核controller sys.executable/venv/活动Core锁依赖及已导入PostgresSaver模块实际来源与distribution版本，再允许其MIGRATIONS决定checkpoint阶段。未实现该门前source入口继续关闭，TargetProof消费摘要显式controller_runtime_verified=false，不能默认为true。

只有同次creator仍持锁的新目标依次真实完成M2原始比较→1–8升级→实际candidate撤销/收据双重放→重放后的最终owner/writer精确ACL与实际PG检查，才可yield不透明TargetProof。最后实查目标身份/owner集合/history8、实际retirement trigger、无其他目标会话/active run/live lease、中央四表空且usage sequence未使用；不依赖之前upgrade的旧ACL回执。proof不是可构造dataclass，私有seal/registry登记本实例且不支持序列化；`consume_target_proof(proof, *, source=原BackupInputs)`原子单次取走，重核creator锁/出生OID、全部实际输入与控制SHA及源绑定，失败也不允许再次消费，context finally总撤销未消费proof。消费的body-free摘要只供记录，不能作为后续入口授权输入。

根另批准mint末次owner事务内取得完整UTC Core/checkpoint/sequence摘要，消费时再次实际ACL与完整snapshot对照mint私有终态hash，防止仅合作creator锁内的外部DML/ACL改变后消费旧证明。正常proof链目标连接16（旧pipeline10+mint实查3+consume实查3），旧public execute未启proof仍原计数。仅证明核验点前后精确状态相等，不证明全程全局停写或原子性；原sequence log_cnt证据保留，不排时间戳或字段来凑一致。snapshot逻辑列与row/sequence摘要不认证所有约束、默认值、索引DDL或完整供应链，正式门继续false。

测试先静态设计、等根审接口授槽：真实完整候选的capture→restore→upgrade→native replay→最终检查→同call单次消费；普通对象/JSON或不完整参数不能生成证明；finally过期、未注册/关闭creator、同名新库OID替换拒绝；实际ledger/控制绑定漂移拒绝；真实replay后ACL或sequence污染拒绝，失败保留目标。另仅必要旧default/公共JSON兼容节点，不重复已有M1/M2/隐私重放绿项。现无新测试运行，native/runtime/Linux/central/publication正式位与源升级入口继续关闭。

静态实现为新target_proof及窄改local_pg/capture_binding/local_restore：M2现在比较创建时registry三OID；公共execute只抽共享context，旧参数/JSON未改；private proof路径没有success.json或旧receipt导入。新独立reviewed pin固定17个实际controller文件，继承M1八控制、capture四控制与candidateReplay的worker/effects/runtime/ledger绑定；旧B1仅generic checkpoint grant函数实际来源受pin，不使用其旧固定候选/restore importer或admission。后续R3只小改fence的existing_only读模式，该文件属原M1八控制，必须双方静态冻结后才生成本片新捕获，避免在途pin漂移。

TargetProof首链`private/safe-narrow-e35fb5589e354bd0b3ff657c881803d6/metadata.json`，03:30:01–03:40:06 +08:00，4 passed/4 failed in604.01s，Asia/Tokyo测试、真实模型/外发/服务器0。正常实际capture/restore/upgrade/replay已抵达mint；4绿为context finally过期且库保留、实际replay后ACL污染拒绝、实际quota sequence使用拒绝，以及default/缺flag零目标副作用+未注册/关闭creator。4红为正常单次消费、同名DB重建OID、实际目标DML、实际ledger字节漂移，均先触发TARGET_PROOF_SOURCE_BINDING，后三预期错误尚未触达。

根与R3已定位同类测试夹具格式差异：repin手建ReleasePin.locks tuple按LOCKS固定序，官方parse按名字排序，strict源对象摘要因此不同。仅在新proof_case捕获之前通过官方BackupInputs.parse(source_document(...),workspace)规范化测试自有源inputs；不修改已捕获dump/旁账/目标，不改生产strict source digest/whole equality或正确断言。根授1槽只复验这4红，原4绿不重复，旧prefix7兼容暂不运行，不能称一次8/8。

仅4红复验为`private/safe-narrow-e721a757b1b44b60b4bf522efd8abec4/metadata.json`，03:42:13–03:47:42 +08:00，3 passed/1 setup error in328.86s。正常实际单次消费、真实同名DB重建出生OID拒绝、真实目标DML漂移/不修回/单次失效已通过；runtime/source/native/Linux等仍false。唯一ledger字节漂移节点在fixture生成M1捕获的候选worker握手阶段，尚未yield proof_case时，由精确sessions检查报INCREMENTAL_OTHER_SOURCE_SESSION（incremental_pg.py:300→117），未触达目标restore/proof/ledger改动。未自动重试、不放宽session硬门，失败日志保留，已向根报告并释放槽；当前为首4绿+后3绿+1setup阻塞，不能称8全绿，旧M2兼容仍未运行。此时本片代码继续冻结，后续fence必要Windows同句柄修复由根与R3另协调，不能在本轮在途改pin。

03:52根批准仅新增ledger节点fixture诊断：先调用原精确sessions，仅同一固定拒绝后再读当前PID/backend_type及allowed PID，随机private目录保存`observation=after_rejection_current`；它是拒绝后的当前集合，不代表原瞬间集合。观测/写文件失败不替换原拒绝，不读取DSN/appname/query/正文，不放宽集合、改会话或自动重试；通过时不造诊断。R3最终fence已冻结SHA256 `0b9b018ef0c3cb24c9fd17472a72a3719f11a1de71830175f1c23b2e35764e91`，根授1槽仅ledger1及旧public M2 prefix7兼容1，已有7绿不重复，不能冒称一次Proof8/8。

最终必要补链`private/safe-narrow-722820d2595b48e39901bd19fae6a3b4/metadata.json`，03:53:06–03:55:34 +08:00，2 passed in147.93s。先只读collect精确确认旧参数ID `[core-only-7]`；实际运行仅新ledger目标与该旧public M2目标。ledger实际在mint后改字节，consume重核文件拒绝、不再重放/修改目标，token也已耗尽；旧public默认管线按最终fence实际完成原始内容绑定→升级，保持兼容。此链没有触发sessions拒绝，不人为造PID诊断；之前setup错误真实原因尚无当时PID实证，不能把维护进程猜测当事实。Proof八节点为首轮4绿+fixture修正复验3绿+此次ledger1绿，另旧兼容1；不重跑7绿，不称单次8/8或9/9。令牌已释放，所有source/controller/native/runtime/Linux/central/publication正式门继续false。

## M3a controller运行时独立组件（03:35定向完成，接线未完成）

新增`tools/first_release_controller_runtime.py`（308行）及专用测试`tests/v4/release/test_first_release_controller_runtime.py`（225行），单函数最长35行。ControllerRuntimePin固定候选/manifest/Core锁、helper与Python实际SHA、Saver distribution版本、init/base实际文件SHA及MIGRATIONS数量/摘要；核已安装活动包的版本、位置、platform marker与Requires-Dist extras闭包。实际模块必须来自当前venv，类/基类/SQL列表身份与setup代码来源匹配；调用verified_saver再次核验当前状态。没有修改旧工具或依赖锁，没有CLI或源写入口。

唯一首链`private/safe-narrow-6820f8813b2a41afabf042644f36fed4/metadata.json`，03:31:39–03:31:46 +08:00，4 passed in6.32s。四个节点分别验证真实3.11 venv及活动依赖闭包正例、实际错误解释器/非venv和hash拒绝、实际已加载Saver替换或SQL变更拒绝、合成锁漏掉真实活动依赖拒绝。正例候选/manifest为显式合成绑定，Core锁为审核副本；不能据此宣称已验真实Git候选、PG、TargetProof或源升级。子进程禁网络/PG连接，清凭据、关追踪、时区Asia/Tokyo；无真实模型、服务器或外发。Ruff E/F/I/B/UP/SIM、format与AST检查通过，未运行全量或重复旧绿项。

## 下一M3a：同call已有源库forward（实施前）

新增仅本机合成fr_upgrade源的stage-aware编排，将实际TargetProof、controller RuntimeWitness及源双栅栏组合，完成Core8→checkpoint→grant；源隐私重放/回填仍单独待做，维护标记不解除。默认只校文件/pin，0连接/进程/写入；apply_source必须显式。既有只读held_source退出时要求旧baseline相同，保持它不变，不能用它包DDL或松锁后凭旧检查写。

专属scope按原顺序取得existing-only文件EX锁与PG EX锁，核原marker、backup-started、全部capture材料、实际cluster/database/role OID、旧4/7精确profile、owner集合、会话和忙run。在同一scope内执行_proved_target，creator仍存活时直接消费真实TargetProof，只在此受控成功路径生成私有SourceUpgradeWitness；消费JSON只能记录。当前source/replay/runtime pin及实际PostgresSaver生成RuntimeWitness，checkpoint前再verified_saver。两个门须同call组合，任一孤立凭据、summary或人工true都不赋予源写权。

Core阶段复用受pin MigrationBundle/forward_core，READ COMMITTED/READ WRITE中按稳定顺序NOWAIT锁原所有业务与检查点表；锁后再核身份、会话、busy、精确旧profile、全capture baseline与材料，才执行候选原SQL与历史追加的一段事务。提交后独立核完整history1–8，按capture原columns做PG UTC/jsonb_agg/C排序摘要，所有旧字段/旧行/时间戳保持；schema_migrations仅旧prefix投影，新增1–8账本另外精确核。checkpoint_migrations旧版本集合在已通过全baseline的前态内实读固定，SDK允许新增的版本另核，不掩盖旧行变化。新业务/中央表应空、usage sequence未使用。

checkpoint是独立autocommit阶段，用刚再次核过的同一个Saver class执行真实setup并核MIGRATIONS完整历史；grant是后续独立事务，仅在旧writer本已精确合法时授予新增运行权限。完整源双锁和原材料跨阶段持有，但这不是一个原子事务。失败记录最后确定阶段；Core已提交后checkpoint/grant失败保留Core8及可能部分checkpoint，不能声称回4/7。提交结果未知标commit_outcome_unknown，失败关闭，不自动重入/清理/回滚或接管prefix8。

新增fr_upgrade窄终态helper，不伪造RestoreContract、不改旧被pinACL入口：复用source_profile.checked_identity核原OID/角色限制，另核schema/关系owner；verify_relations/table_acl按QUOTA实际差异核writer权限，其余表DML/账本只读/序列仅SELECT与USAGE，无grant option/DDL/TEMP/owner/PUBLIC越权；routines(inputs,7)/triggers(7)核实际函数与挂载。单独核完整8历史、SDK历史、中央四表空/sequence未用、owner/session/busy以及允许的阶段变化。旧只收prefix4/7的source_scope不能作为8后验。

首链至多8个必要新节点：合法4、合法7的实际Proof/runtime/source全链；默认0副作用；未注册/失效Proof在首写前拒绝；实际runtime不符首写前拒绝；capture后源真实漂移在锁后拒绝；Core已提交的checkpoint故障保留8/marker且阶段准确；未知提交结果受控失败关闭且不自动重入。已有0006原生事务回滚绿例不重复。先静态冻结接口再授测试槽，不因低层helper通过宣称整个source升级已完成。

后续M3b必须独立受pin的fr_upgrade/OID/真实PID候选worker，按原生apply自身事务边界落实源既有撤销双重放与独立擦除后验，再候选backfill preview→apply→second=0；不得宽化fresh fr_restore worker或外套大事务。此片即使成功也只报source_forward_completed、privacy_replay_pending/backfill_pending；全局停写、正式runtime/Linux/central/publication仍false。

### M3b接缝细化（04:18只读设计，尚未编码）

源进程仅在同一活SourceUpgradeWitness的Core/SDK/grant确定完成后启动，独立审核pin绑定原fr_upgrade库/角色OID、父PID、候选/manifest、最新旁账、实际Python/Core锁及全部控制文件。复用受审纯stdlib bootstrap、CandidateFinder、runtime及导入来源核验；不构造假RestoreContract、不放宽现fr_restore worker。子进程只用真实源owner连接，握手实际PID，父侧精确核会话集合再ACK；外部JSON与application_name不赋权。

仅max_size=1不足以保证后续仍是同连接：实际ConnectionPool可能在断线后补新PID，native LangGraphRuntime.purge又直接借repo.pool。因此需先独立实现受pin物理checkout门，覆盖所有pool借用与提交后purge、核真实Connection身份/PID，拒绝替换而不自动重连/恢复。不能只包repo.transaction或改_local，也不能以一次握手替代后续连接核验。实现前仍须审阅实际pool的所有调用点与事务副作用。

源effects可复用原观察器的snapshot、central、legacy/span/erased等只读函数，不能借用自行新建repo及新目标回执的replay总控。调用真实候选apply_withdrawals自身全owner事务，结束后才原生checkpoint purge；第一遍独立擦除检查、全状态与导出，第二遍必须全状态及导出严格相等，中央四表/sequence保持。失败保留阶段，不重放重试、不加外层大事务。

物理连接门首片限定新增source_pool helper及专属真实PG测试，不接source worker/forward或改业务。使用原真实repo.pool和Connection，只从保存的原getconn借一次并长期持有物理lease；临时包该实例getconn/putconn，原pool.connection和Saver类型判断不变。每次逻辑借/正常还，在业务事务外核autocommit/dict_row/IDLE、相同对象/PID/backend_start、PG15实际DB/角色OID/位置、父PG独占栅栏和精确会话集合；禁止并发、嵌套逻辑借用和跨线程，仓库原生嵌套事务仍用_local复用。失败永久poison，不commit/rollback或补连接；退出先close pool再原putconn一次，保留业务首错并优先进程控制异常，恢复实例方法但pool不重开。期待身份是未来受pin父子协议的受信输入，本helper不核SID、不独自授予源写权。先静态审阅，最多四个独立PG行为再授槽，现尚未测试。

04:43下一片实施前：新增source_process/source_worker/source_effects，不修改仍在途的Forward/scope或旧fresh-target worker。source_replay(witness,pin)仅接活source_forward_completed凭据；独立pin绑定ForwardInputs及完整forward pin、candidate/manifest/三锁、原最新旁账、Python和所有实际控制SHA。新worker纯stdlib启动、核来源/实际K3运行时后创建真实候选repo(initialize=False,max1)，经已验pool lease保留一条只读物理连接；ready_ro只发nonce/request hash/实际PID与OID。父持原file/PG锁、核活凭据和准确实际会话后ACK；ACK之前不得启写。实际native双重放遵循原全owner事务及提交后purge，不外套事务，独立擦除/中央状态与第二遍全状态/导出相等。最终receipt须在child连接仍活时等待父done ACK，父以真实PG完整终态对照后才放child退出，避免已关连接后凭旧PID放行。只有固定body-free JSONL阶段/结果，未知提交/超时立即保留现场，不重试/清理；初始组件测试不得冒称完整controller admission通过。主入口接线与回填仍另待，先静态审阅新实现再授槽。

04:57静态接缝补充：父端有界read/send/cleanup另拆唯一source_protocol helper并纳入DIRECT实际hash，使process保持400行软目标。清理普通异常保留原业务首错，进程控制异常优先同对象传播。worker收到write_ack后首写前取得的完整state_before，必须严格等于此前双方核过的ready_ro state；父最终亦复核同一绑定，不能仅在已写后才发现ACK间隙的持久源漂移。此为前后核验点约束，不声称消除瞬时不合作写入；不新增外层事务或session豁免。

随后只对独立pin明确允许owner调用候选backfill(MemoryService(repo),owner,apply=...)。preview不得改变全状态；repeat的message_metadata/search_tokens/assistant_created变化计数必须全0，其他只读计数不误当变化。原字段变化只允许既有backfill契约的四项metadata；助手新消息必须有原生稳定ID/有效来源，revision/operation新行精确对账，另一owner、撤销、收据、checkpoint及中央状态不变。源双重放与回填分片定向测试，未知提交结果/提交后purge故障均停，Linux、prefix8中央身份保全及正式发布不因此放行。

04:56只读核对实际backfill接缝：签名为backfill(memory,owner,*,apply=False)，实际变化数仅message_metadata/search_tokens/assistant_created；invalid_time、assistant_existing、assistant_skipped不要求归零。原生backfill在repo.transaction(owner)内取owner事务锁，preview也取锁但不写；不能把此前privacy apply及提交后purge包进此事务。四项例外只指data JSON的thread_id/at_ms/origin_conversation_id/search_tokens；0007 generated search随合法search_tokens改变，后验须按真实生成规则核验，不能盲排该列。每条原生record_assistant还新增core_operations并使本owner revision精确+1，须与assistant_created及稳定msg_指纹ID逐项对账，不能把owner行全冻结或任意忽略revision。原消息正文/revision/时间戳、另一owner、撤销/收据、checkpoint与中央状态仍须保持；新助手只用真实有效原话/fact/claim及原run.updated_at。后续最多用1–3个真实旧成功run夹具验证，不重做300轮或复制旧绿项。

## Artifacts and Notes

### M3b回填进程接线下一片（2026-10-24 05:35 +08:00，实施前设计）

源replay组合链在途时，其全部既有控件冻结。后续回填不把成功dict当作写权：增加独立SourceBackfillPin，完整绑定原ForwardInputs、原SourceReplayPin摘要、候选/manifest/三锁/最新旁账/Python及新旧实际控制文件。仅显式传该pin且同时有有效replay pin时，execute才可在首I/O前校验；默认None保持旧行为。真正调用必须仍在原creator、源file/PG锁与同一活SourceWitness内，且真实phase已source_replay_completed。源privacy与提交后purge不包进回填事务，不允许另一次调用接管prefix8。

新source_backfill_process/worker作为独立小片复用已冻结的源协议纯读写/清理、实际peer代际/state查询、受pin source_worker的候选导入/运行时/物理lease基础；不改在途旧worker。新worker严格独立形状/本机身份及控制hash，纯stdlib启动后才导入真实候选MemoryService、mingjing_core.memory.backfill.backfill、tokenized_payload/fingerprint及effects组件。所有被调用函数和已加载业务模块均从同一不可变候选manifest核验；不能拿控制树MemoryService或成功dict替代实际业务调用。若候选自身尚无effects helper则明确拒绝，不借未绑定文件补齐。

父子ready_ro→write_ack前核同一实际PID/generation/单物理连接、完整初态和活栅栏；回填首写前再次核ready初态。对原source owners全集按确定顺序逐owner调用已验证verify_backfill_effects，每个owner用原生owner事务、preview不写、首遍逐值/operation/revision/generated search精确核、second三个写计数0且全态不变；前一个owner已提交而后续失败时保留现场，不能声称全库回滚。只传固定phase、有限计数和摘要，owner/样本ID仅hash。最终父在child仍活时核完整状态，再ACK关闭；清理和控制异常保持原优先级。

源码拆分以400行/函数60为目标，不引入通用外部callback赋权或新CLI。先审两个core4/撤销后回填组件行为，再审完整候选worker和同call接线；只跑新增必要目标，原组件/源组合已绿项不反复跑。此段仅后续实施前设计，新pin/worker/接线均未实施或验证，所有正式位与Linux、中央身份、切换门仍关闭。

### M3b同call接线下一步（2026-10-24 05:09 +08:00，设计待实施）

两条在途链全部停止并由根审阅后，才允许窄改Forward接线。拟execute(request,*,apply_source=False,source_replay_pin=None)：非None时必须精确SourceReplayPin并在任何连接/进程之前完成其独立绑定校验；默认不传保持原接口/回执和零副作用，传pin而未apply仍只校文件。不要引入任意callback或允许外部构造SourceWitness。

仅在现_apply仍持原目标creator、源file/PG锁与活_authorized witness时，先真实完成_stages，取原目标/运行时摘要，再调用source_replay(witness,pin)。该接线必须在witness finally撤销之前完成；不把成功JSON重新认作权限，不在单独第二次调用接管已到prefix8的源。正常外层phase取source_replay_completed，privacy_replay_pending只在真实返回后才false，backfill_pending及所有正式发布位仍保持原关闭状态。未知提交、child握手/最终状态不符或清理故障按最后实际阶段上交，维护不解除，不重入/修复。

必要新验证限两个行为：真实非空prefix7经M1→同call目标证明/运行时/forward→实际新源worker双重放的完整组合正例；新pin默认校验零连接/进程及错误type/候选绑定在首I/O之前拒绝。复用已通过组件的真实native种子与原始内容/独立擦除观察，不伪造proof或witness，不重复已绿组件故障矩阵。此设计尚未实施/运行，不能当作源隐私闭环已完成。

唯一窄链在`C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep`运行：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep tests/v4/release/test_first_release_incremental_backup_pg.py

私有证据为`private/safe-narrow-8674777b249649a1a896d97a214faef8/metadata.json`（2026-10-24 01:58:48–02:00:26 +08:00），同目录pytest.log/XML；8 passed in 96.61s，模型/外发/服务器均0。两个prefix正例、默认零副作用与错OID、冒用pg_dump名称的额外会话、live lease、跨进程共享文件锁/PG锁、同快照与新鲜源漂移共8目标。Ruff E/F/I/B/UP/SIM及120列format通过，五个Python文件346/398/206/114/383行，最长函数57行；无全量或重复已通过目标。

根审补充安全目标单独证据为`private/safe-narrow-c177329d63294615be127f8e0d638c15/metadata.json`（2026-10-24 02:02:36–02:02:53 +08:00），1 passed in 16.79s。单一child先经真实cooperative_writer共享锁写入synthetic-writer-before并关闭会话；真实backup完成且释放文件/PG锁后，同child再经相同协议获得共享锁，因保留marker受控拒绝第二行。直接PG确认完整表/sequence状态不变、只存在首行且marker仍保留。此为8/8之外的1/1，不合并宣称一次9/9；测试文件现445行，已记录根审软目标例外。

## Interfaces and Dependencies

显式FIRST_INCREMENTAL_OWNER_DSN/WRITER_DSN只允许本机55480/55481和本次fr_upgrade库、精确角色；FIRST_INCREMENTAL_ADMIN_DSN限同一服务器的postgres/core_test_main控制库；所有PG隐式环境拒绝。子进程有限环境，密码只在内存，不进入argv/回执/日志；只调用已pin真实PG15 pg_dump与Python3.11 venv。源状态摘要不是原始恢复内容核验，backup_captured也不构成升级/恢复/native/Linux/供应链/发布授权。

## Outcomes & Retrospective

08:24 +08:00 当前诊断片：实际 held 原生候选中，外来owner连接使同次观察精确2 PID、busy_run_count=0/other_session=true；关闭后实际failed运行带未来lease使busy_run_count=1/other_session=false、仅观察PID。原错误码、严格拒绝和consume烧毁token不变，附原观察JSON note且不后查；首链1/1只证明诊断行为，原07db CI红的根因仍未知。控件自身已有受hash pin，新调用需重新审新pin；没有授源写入、正式恢复、Linux或发布能力。原导入失败单独保留，不与本链合成第二个业务目标。

M1统计observer本机必要两目标首次2/2通过，唯一原证据为`private/safe-narrow-bbbcd541aa36476f9f1306035f965f1e/metadata.json`及同目录pytest.xml/log，07:47:43.682–07:48:30.416 +08:00、45.86秒，真实PG15.19、清凭据/关追踪/TZ Tokyo、真实模型/服务器/外发0。原七字段有限诊断、五个原精确PID门、旧候选runpy snapshot导入与独立pin闭包保留；旧8控输入不再适用，必须新capture/新9控pin。原CI额外PID均保留未知，新观察不能保证CI转绿；原脚本69/81、Linux应用/正式CLI/中央身份/全局writer和发布门仍关闭。

07dbf97已推送，源码与新增组合测试/两份草案随小片提交。新push CI待核；091 push旧CI的精确失败和执行边界见Progress及唯一GitHub run40031494831/job120680561852，未另抄日志。当前首发仍No-Go，任何后续CI绿不说明旧额外PID的身份或根因。

源回填窄修后唯一两目标证据为`private/safe-narrow-9c3f5320aa34482db560b8b5773bc14d/metadata.json`与同目录pytest.xml，2026-10-24 06:49:06–07:07:31 +08:00，2 passed/1既有AnyIO warning in1103.49s（正862.120秒、负240.801秒）。实际候选09173ac46b47dd29cd7298bb253a8c5d326b8c42、两个候选helper来源、M1/TargetProof/Runtime/Forward/source_replay/source_backfill实际六阶段与四次活peer观察通过，closed已完成。两个历史助手完整稳定ID/血缘/policy、四项源metadata和生成搜索、首遍精确变化及二遍三个写计数0/全态相等均通过；旧fact/run/Outbox/SDK擦除，SDK1/1/1→0/0/0，纠正完整fact及Bob全owner行保留。fresh原生13项bool、真实native export/full source state、中央四空表及sequence、维护材料后验全部通过；source_upgraded/source_write_authorized/native/runtime/Linux/central/global_quiescence/publication正式位仍全false。清凭据/关追踪/TZ Tokyo、真实模型/外发/服务器0。前两轮失败如下原样保留，未合并为历史一次全绿；正式CLI、既有中央身份保全、实际应用writer及Linux门仍缺失。

源回填唯一原红诊断复验为`private/safe-narrow-f554e55fa7e945438d3606a3e747cab7/metadata.json`及同目录pytest.xml，2026-10-24 06:31:00–06:45:58 +08:00，1 failed/1既有warning in897.18s。XML实际候选09173ac46b47dd29cd7298bb253a8c5d326b8c42、阶段source_backfill_3_owner_verified、会话恢复True，有限peer事件恰为replay ready/final和backfill ready/final四项。仍为SOURCE_REPLAY_PROTOCOL_TIMEOUT_OR_INVALID，未完成closed确认及新测试独立history/privacy/全态末段，不将这些事件等同整链通过；原首链与本红分别保留，原负例不重跑，正式门仍关闭。

源回填首链唯一证据为`private/safe-narrow-65c64c87ab0a411ca1f7b478a518530f/metadata.json`及同目录pytest.xml，2026-10-24 06:08:59–06:28:35 +08:00，1 failed/1 passed、1既有warning in1175.78s。正例896.632秒仅记录Forward固定通用协议错误，无阶段/peer或完成组合证据；负例278.416秒确认默认及非法独立pin零副作用。调用前历史seed及候选/helper hash验证到达，但未在XML保留candidate值，不将批准的archive起点当实测属性。实际三阶段是否提交、独立后验与正式关闭位末段未触达，均不得称通过；真实模型/服务器/外发0。控件与原始证据保留，源回填及正式门继续未放行。

原源replay失败节点的唯一复验为`private/safe-narrow-753e531394c541199b423beeac76e2e7/metadata.json`及同目录pytest.xml，2026-10-24 05:54:51–06:05:35 +08:00，1 passed in642.87s；同9be44b9实际候选、原20行生产接线不变。JUnit实测fixture_seed_timezone=UTC、13项固定观察bool全true，含保留fact完整行hash、原话/上下文/FTS/embedding；末段真实同候选原生export、完整源state、中央四空表/sequence、维护材料及正式关闭位全部通过，SDK三表1/1/1→0/0/0。新fixture292行/最长42，原NATIVE/旧测试/生产/超时未改；清凭据/关追踪/TZ Tokyo、真实模型/stage生产/外发0。原e2首1红1绿与本1绿分轮保留；只证明本机prefix7非空源组合和原默认拒绝行为，源回填、Linux、正式CLI/中央身份/切换仍未完成。

新组合首链唯一证据为`private/safe-narrow-e2a970f563034375bddded36fe0a934a/metadata.json`及同目录pytest.xml，2026-10-24 05:34:13–05:48:42 +08:00，1 failed/1 passed in868.26s，实际候选9be44b9376004e27d42e048fad8d2af73e9f5dd8。失败节点719.355秒，在真实scope/proof/runtime/Forward/replay返回并核过ready/final实际同PID代际、独立旧fact擦除、run/Outbox/SDK、纠正事实完整行及Bob全owner表后，fresh观察all布尔红；尚无具体False项证据，后续原生export/全态/中央独立断言未到达。默认有效pin零IO及错type/候选前置拒148.281秒通过。清凭据/关追踪/TZ Tokyo、真实模型/stage生产/外发0；不称完整组合通过，原生结果摘要不是可重用权限。

回填core4与撤销后组件唯一首链为`private/safe-narrow-cc6b12e50a91424dbe9da16c3ffa4abd/metadata.json`及同目录pytest.xml，2026-10-24 05:37:57–05:38:03 +08:00，2 passed/1既有AnyIO弃用warning in5.23s。真实core4采用唯一实际fact，精确缺助手gap经首遍完整payload/稳定ID/血缘/operation/owner增量核验重建1条，run未改、second三个写计数0。另一节点实际run:e0三SDK表1/1/1在retire后仍保留、原生apply提交后purge归0/0/0，正文/FTS/助手/运行输出清空；第二apply全态不变，再backfill创建0且全态/旁账不变。测试200行/最长33、静态通过，清凭据/关追踪/TZ Tokyo，真实模型/stage生产/外发0；仅当前业务组件，fresh candidate/source admission/legacy映射回填与Linux仍未覆盖。

会话诊断唯一窄复验为`private/safe-narrow-7eee62eabceb437babf3b069e98a1c52/metadata.json`，2026-10-24 05:22:55–05:23:24 +08:00，2 passed in28.60s。原CI失败prefix4实际capture/restore比较通过；另真实额外连接负例确认原gate PID/type集合包含它、仍拒绝、源全态不变且无维护标记。TZ Tokyo、稀疏凭据/关追踪、真实模型/stage生产/外发0，未重跑大套件。它证明新诊断和本机必要路径，不揭示此前CI那次额外PID，也不证明新Linux CI通过；旧失败仍保留，No-Go不变。

SourceForward两点窄修的唯一补链`private/safe-narrow-630c504e49b048d982b908c1989ad913/metadata.json`，2026-10-24 04:58:10–05:19:02 +08:00，2 passed/1 failed in1250.85s。post-setup漂移419.888秒与prefix7正例445.150秒通过，均实际SDK10→10/new0，漂移时未尝试source grant；控制故障385.213秒目标同interrupt对象先通过，后被新fixture错误类型断言拦住，不能称三项全绿。待核原M1诊断变化后只复验这1红。

回填effects唯一首链`private/safe-narrow-04ae4c3ec6284fc8a71c28936a7675d7/metadata.json`及同目录pytest.xml，2026-10-24 05:19:18–05:19:24 +08:00，2 passed/1 warning in4.16s。两个真实core3历史、Bob原话/收据与实际SDK checkpoint/blob/write夹具验证preview全态不变，first四metadata逐值/generated search/助手稳定ID完整payload/operations/owner revision精确对账，second三个写计数0且全态相等；另一节点在真实metadata/首助手/operation/owner增量已在事务内写入后抛同一普通异常，完整回滚到before。三个文件182/224/149行，Ruff/format120/AST通过；唯一warning为既有anyio别名弃用，未扩大修复。清凭据关追踪、TZ Tokyo、真实模型/stage生产/外发0；不证明fresh-process候选来源、SourceWitness或源全过程，core4/legacy/撤销后回填未覆盖。

正式PR合成候选a1e1bba本次CI仍失败，不能因来源7e2曾绿、本机绿或另一push检查仍在途称d40本轮通过。原GitHub日志是唯一来源run40018148231/job120635461896，不另复制日志或正文。同次会话诊断与两节点窄复验已完成，证据见本节首段；旧Linux根因未知，新CI未验证。完整脚本、源组合接线及正式发布门继续关闭。

源replay进程组件唯一首链为`private/safe-narrow-6b91b99492b343b6868f3ab6b7a1832d/metadata.json`及同目录pytest.xml，2026-10-24 05:03:20–05:09:43 +08:00，4 passed in381.18s。真实prefix7→8组件的native更正旁账使旧正文superseded→deleted空data、旧run stale→revoked且输出清空，三类checkpoint实证1/1/1→0/0/0，第二遍完整state/export相等，中央四表/sequence保持；父最终核验时child实际PID/generation仍活。另覆盖prefix4→8组件无write ACK不写、ready/ACK间隙持久DML首native之前拒绝、final持久DML拒DONE并保留已提交native，以及伪opaque/错pin不启动进程。五文件389/339/135/71/271行，函数上限60，Ruff E/F/I/B/UP/SIM、format120、AST通过。清凭据关追踪/TZ Tokyo，真实模型/stage生产/外发0。测试是中性实际迁移+真实候选worker组件，不是完整SourceWitness控制器链；未做源回填、初始连接失败/进程控制故障注入或Linux，正式门仍关闭。

新增回填effects片已有上述2/2组件实证，尚未接入受pin候选进程或SourceWitness。成功dict不是权限；候选进程来源、父终态绑定及整链验收仍须分别实证，不解除Linux/中央保全/发布门。

SourceForward唯一原红节点的夹具修正后复验为`private/safe-narrow-701fefd1fa2446379869ebc280ebd25f/metadata.json`及同目录pytest.xml，2026-10-24 05:23:23–05:29:34 +08:00，1 passed in370.57s。真实native SDK闭连cursor故障发生，新增DDL未执行；原KeyboardInterrupt对象优先于普通SDK/cleanup错误，完整Core8、旧行、持久marker及registry断言保持。SDK仍10→10/new0；原2绿未重跑，未将各轮合并成一次全绿。清凭据关追踪、TZ Tokyo，真实模型/stage生产/外发0。

SourceForward原实现首链唯一证据为`private/safe-narrow-8095e97cff4b416fb43ca9d3c51fbd93/metadata.json`与同目录pytest.xml，2026-10-24 04:15:19–04:54:43 +08:00，8 passed in2363.75s。默认零副作用、prefix4/7完整同call组合、普通对象及真实PG解锁、实际runtime不符、NOWAIT锁后真实源漂移、Core已提交后真实SDK闭连故障与提交后控制边界故障均通过。两个SDK计数均10→10、新增0；所有源重放/回填、应用全局停写、正式恢复/runtime/Linux/中央保全/发布仍未完成，维护标记保留。测试清凭据关追踪、TZ Tokyo，真实模型/服务器/外发0。两项额外审阅缺口尚未验证，不以原8/8覆盖它们。

CI失败的两个目标唯一窄复验为`private/safe-narrow-cda463c8c84c4a91bdef89b825cde12a/metadata.json`，2026-10-24 04:48:08–04:48:42 +08:00，2 passed in33.51s。实际K3 host、隔离PG15、TZ Asia/Tokyo、清凭据关追踪，真实模型/服务器/外发0；原4163绿项不重复。此次未触发会话拒绝，未生成原拒绝瞬间实证，根因保持未知。解释器夹具的Linux验证及更正后分支CI仍待完成；已有Linux CI失败记录不覆盖。

M3b物理连接基础唯一首链为`private/safe-narrow-a5d9a0e458454a89ab909c4cf563f72e/metadata.json`，04:35:10–04:35:43 +08:00，4 passed in31.93s。实际K3 host、真实隔离PG15、TZ Asia/Tokyo、清凭据关追踪、真实模型/服务器/外发0。正常节点保持原repo嵌套RR连接与快照、原SDK三表实际各1→0、业务普通异常同对象；三负例证明真实closed/foreign/额外session固定拒绝、无第二次物理get或替换连接、foreign仍可用及registry失效。helper383行/最长48，测试183行/最长45，Ruff E/F/I/B/UP/SIM、120列格式、AST及diff通过。只证明本机已pin后的连接约束，不证明初次失败无重试、控制故障注入、SID/父子握手或源双重放/回填；正式恢复/runtime/Linux/central/publication继续关闭。SourceForward首8仍在另一进程原样运行，未与本4节点合计。

source_postcheck组件的7个独立行为已有6+1分轮真实PG实证，保留原类型故障被PG触发器依赖拒绝的夹具失败，不称一次7/7。helper330行、专属测试256行，单函数最长44行；Ruff E/F/I/B/UP/SIM、120列format及AST通过。实际4/7原状态捕获→Core8→SDK setup→grant仅为测试夹具，分别验证只读owner/writer终态与拒绝后不修复；不是默认或既有源写命令，也未实证同call Proof/runtime/双栅栏写入组合。SDK新版本数为0，未覆盖发生待应用SDK迁移的旧版本升级。所有source_write_authorized、global_quiescence、正式runtime/Linux/publication位仍false，SID不由该helper声明已核。

Source guard只读基础已分轮覆盖12个行为，保留首轮whole-input夹具错误与第二轮真实Windows锁读故障，不合并为一次全绿。最终guard/fence/新测试分别233/134/268行，单函数最长60行；Ruff E/F/I/B/UP/SIM及120列format通过。原维护marker/backup-started均不删除或补造，实际源状态不被修改/自动修复，source_upgraded、正式native/Linux/central/publication仍关闭。此片没有实现SourceUpgradeWitness、fresh表锁后前向写、源隐私重放/回填，也未验证与完整目标证明/运行时门组合的源升级入口；新source_postcheck独立组件已按上述范围取得真实PG证据，尚未接入源编排。

controller运行时独立组件的四个实际进程/依赖/已加载模块行为已定向通过；其opaque凭据仍未接入后续源guard与迁移编排。TargetProof八个独立行为现按4+3+1分轮实证，另必要旧public prefix7兼容1；只证明仍持creator锁的新目标链及前后真实终态一致，controller_runtime_verified/source_write_authorized仍false。不能由独立运行时组件的摘要替代same-call目标恢复/原始内容/重放证明，也不能仅凭TargetProof写源。source_upgraded及正式native/Linux/central/publication继续关闭。

本机合成已有库M1备份入口已有旧版8/8及独立marker1/1证据；M2新增UTC/列集合/lineage捕获与同call新目标原始内容绑定，八个新行为按3+3+2实证。M2只证明本机原始内容匹配，仍未实现整个“源捕获→原始恢复→重放→前向源fr_upgrade库”的放行链。现应用未接栅栏，global_quiescence_verified=false；before_after不排除dump期间瞬时非合作连接。source_restore_content_verified/source_upgraded保持false；逻辑列map不认证默认值、约束、索引/触发器、类型定义或所有DDL。源prefix8/中央账本身份保全、正式恢复、Linux与发布均仍No-Go。测试自产审核pin不认证审核人或完整供应链。没有业务迁移、依赖、既有权限或原b9变更。

M3a第一基础片仅内部中性Core SQL原语与prefix4/7只读profile，148/213行；新PG测试250行、最长函数55行以内。Ruff E/F/I/B/UP/SIM及120列format通过。真实PG定向6+2已验证上述基础行为；中性grant原语尚未被新入口调用，PostgresSaver checkpoint阶段、完整源状态/运行时门、typed单次证明、源编排及M3b源隐私重放/回填都仍未完成，所有正式门保持false，不给生产/既有prefix8或额外关系开口。

## 修订记录

- 2026-10-24 07:49 +08:00：记录M1同次统计观察真实两目标首次2/2及根审的实际边界，唯一证据只在本计划登记，旧CI失败与正式No-Go保留。

- 2026-10-24 07:44 +08:00：只读核对f6 PR合成检查的新两处会话拒绝与X02取消状态，分清push/PR实际checkout及未执行步骤，不复制完整日志或自动重跑。

- 2026-10-24 07:42 +08:00：保f6握手前ACK失败的实际集合与未执行步骤，先写M1限定同次有权限统计观察设计；不改变严格拒绝或推断额外PID根因。

- 2026-10-24 07:14 +08:00：登记07已推及091实际CI setup失败、原瞬间会话集合与后续未执行检查，保精确硬门/未知根因；不自动重试，切累计预算。

- 2026-10-24 07:10 +08:00：记录窄修后受影响两目标真实2/2、closed与独立后验完整通过；保留此前两轮失败和唯一根因未知，区分091 archive与新控制代码，所有正式门保持关闭。

- 2026-10-24 06:56 +08:00：只记一次既有PG容器Python入口只读核对的准确范围，不假称Linux应用可运行或继续环境修复。

- 2026-10-24 06:48 +08:00：记录单新文件去重根审完成，说明为何新增一次受影响validate负例与原红共同验证；不放宽硬门，不追加宽回归。

- 2026-10-24 06:47 +08:00：记录仅原红的阶段/四事件实证及明确未完成的收尾，先写无缓存去重方案；不猜唯一根因、不延长协议、不反复跑绿项。

- 2026-10-24 06:35 +08:00：记录来源CI绿后实际普通集成/推f6fb及X02独立已验片836，不把关联PR绿当原失败根因；补仅回填原红的唯一复验在途，保全候选与测试边界。

- 2026-10-24 06:29 +08:00：保留回填首链1红1绿与可知/未知边界，先写唯一红的有限失败侧诊断计划；不猜阶段、不延时、不重跑绿项。

- 2026-10-24 06:24 +08:00：保留当前源回填唯一链在途，记录三项独立真实剩余项及下一实现先核写入口的决定；未加重复预检或扩大正式位。

- 2026-10-24 06:17 +08:00：记录实际06:14正式push CI成功后的普通远端feed快进；分清PR合成/新feed检查与旧本机树，补唯一新回填链在途，不增加测试或现场诊断。

- 2026-10-24 06:08 +08:00：091片推送后实施独立回填可选pin的最小接线并静态审阅，新增全链测试未开始；保父CI与全部正式No-Go。

- 2026-10-24 06:05 +08:00：记录唯一原红复验1绿与13固定bool、最终独立观察完整通过，更新当前源replay组合状态；保留原红/不同轮次与正式No-Go，静态回填WIP不冒已验功能。

- 2026-10-24 05:55 +08:00：记录父来源5a CI成功与新9be仍在途的各自身份，不把父绿或真实阶段已返回充当尚未通过的新组合/发布门。

- 2026-10-24 05:53 +08:00：补实际PG默认Taipei的只读证据与仅新fixture规范UTC授权，禁止把待复验假设写成已修根因；下一仅原红，不重跑绿项。

- 2026-10-24 05:51 +08:00：保留源组合首链1红/1绿、已触达与未执行断言边界，记录时区假设仅待核及允许的有限测试诊断；禁止拿部分成功充组合验收。

- 2026-10-24 05:46 +08:00：记回填三新文件静态及根审范围、逐owner实际commit口径和测试未开始；原Forward/source worker在途绑定不变。

- 2026-10-24 05:38 +08:00：记录新增两节点真实core4/撤销后回填首次2/2，明确SDK实际schema定位、无原生替身和未覆盖范围；不与旧两组件合成同次4/4。

- 2026-10-24 05:35 +08:00：先写独立回填pin/fresh worker与同call后续接线设计，保当前两节点源组合控件冻结；明确多owner非原子提交、候选代码来源和父活连接终态，尚未实施。

- 2026-10-24 05:34 +08:00：记录9be分片推送、d40 push与PR合成CI真实差异、799源绿后普通集成9f2506f，以及下一可选pin接线的实际未验证状态。

- 2026-10-24 05:30 +08:00：记录唯一原红复验1/1及真实SDK/中断断言，冻结当前已验证组件供小提交；更正当前态的旧待实施文字，历史失败与未来组合/Linux门保留。

- 2026-10-24 05:26 +08:00：记录同次有限会话诊断实施与两节点唯一2/2，保原精确硬门与未知根因；原共享文件软目标例外和CI YAML解析有据，不扩大恢复/发布位。

- 2026-10-24 05:20 +08:00：保留源补链2绿/1新fixture类型错误及实际驱动源码依据，只准修一红；记录回填effects唯一2/2及完整逐值/回滚范围，原其余绿项不重跑。

- 2026-10-24 05:18 +08:00：保留PR #12合成checkout真实CI 4237绿/1会话失败，不与push head结果混用；写原瞬间安全诊断实施前设计，CI上限60→90分钟保留全部检查，源在途控件未改。

- 2026-10-24 05:11 +08:00：标题/背景/目的更新为现有M1–M3分片范围，区分历史686、原首8候选5b和新组件5a，不把工具头、测试archive与最终发布包混用。

- 2026-10-24 05:10 +08:00：记录新源worker组件唯一真实4/4、首遍独立擦除/第二遍全态与活PID终态ACK，以及真实漂移后的保留状态；未把组件提升为同call SourceWitness/首发完成。

- 2026-10-24 05:09 +08:00：先写M3b同call接线的最小可选独立pin接口与两行为验证计划；所有在途控件保持冻结，必须原两链停下并根审后再动代码。

- 2026-10-24 05:06 +08:00：回填精确后验实施前计划，限定两个新helper与最初两个组件目标，保留core4/撤销后验和受pin进程接入待做；不碰在途冻结代码。

- 2026-10-24 04:57 +08:00：源重放静态预审批准唯一纯协议helper分片，补首写前ready状态与最终receipt初态的严格绑定；仍待完整静态冻结及授槽，未宣称接线通过。

- 2026-10-24 04:56 +08:00：只读核对后细化M3b原生回填接缝，明确generated search与owner revision合法变化须精确对账、三个写计数归零口径和owner事务边界；本项尚未编码或测试。

- 2026-10-24 04:55 +08:00：记录SourceForward唯一首链完整8/8及真实SDK10→10、新0、真实闭连和控制边界故障的准确范围；仅在原链结束后允许两点窄修，后续三个必要目标另记证据。

- 2026-10-24 04:49 +08:00：保留88f1d27真实CI一失败一setup错误，窄修解释器测试路径及失败侧会话诊断，两个失败节点仅本机2/2复验通过；另记录04:43 M3b进程接缝实施前约束。源在途控件、生产strict会话门和所有正式发布位未变。

- 2026-10-24 04:36 +08:00：记录M3b物理pool lease实施前接口、静态清理修正及唯一真实4/4首链，明确未接source worker和未覆盖故障；SourceForward首8在途，不动其控件或重跑绿项。

- 2026-10-24 03:44 +08:00：根已追加下一M3a同call source forward实施前设计；新source_postcheck/helper测试目前仅静态，未接源编排、未验证PG。本项记录已发生设计来源，不补造小时进度。
- 2026-10-24 03:56 +08:00：记录source guard两轮真实红与最小夹具/Windows同句柄修复，再分别仅复验受影响4项及最后未执行4项；12行为按分轮证据成立，源升级与正式门继续关闭，冻结三代码路径供根统一审阅提交。

- 2026-10-24 01:39 +08:00：创建独立增量M1计划，先于编码明确实际备份与合作性栅栏边界。
- 2026-10-24 02:00 +08:00：记录唯一真实8目标链全通过与snapshot/序列实证；保留全局停写、原始恢复绑定及正式发布关闭，冻结六路径待根审阅。
- 2026-10-24 02:02 +08:00：单独补根审要求的marker持续防实际写入1/1证明，不重跑旧8项；业务实现不变，再次冻结六路径。
- 2026-10-24 02:07 +08:00：按根指令仅记录M2原始恢复绑定的最小接缝与信任边界，等待确认后才实施。
- 2026-10-24 02:32 +08:00：完成获批新UTC/columns/lineage捕获与M2同call实际原始恢复绑定；保留两轮真实失败，分别修显式DSN及捕获前合法fixture范围，只复验失败目标，冻结五路径交根审阅。
- 2026-10-24 02:49 +08:00：M2推送后只读核对现迁移/ACL/backfill调用，记录M3a/b最小接缝、非原子阶段和源隐私重放边界；未编码、未运行测试。
- 2026-10-24 03:05 +08:00：获批M3a分片先静态实现两个独立helper，采纳READ COMMITTED、真实trigger挂载、PUBLIC授权、单次内存证明与后验顺序硬门；未改R3冻结的旧工具，未运行测试。
- 2026-10-24 03:10 +08:00：根授1测试槽后新基础片首链6绿2夹具比较失败，保留真实证据；按根审只校正合法账本append的旧行范围，单独复验2正例通过，冻结四路径交审，不重跑其余六绿。
- 2026-10-24 03:35 +08:00：记录独立controller运行时组件唯一4/4实证与合成候选绑定边界；保持TargetProof组合、源编排与正式发布关闭，单独提交已完成小片。
- 2026-10-24 03:47 +08:00：TargetProof首8为4绿4strict源夹具绑定失败；按根审仅捕获前官方parse规范化fixture后仅4红复验3绿1 M1握手session setup错误。保留两轮真实结果，未自动重试/放宽硬门，旧compat未跑，释放测试槽待根协调。
- 2026-10-24 03:55 +08:00：按根审增加仅新ledger fixture的拒绝后PID/backend_type私有诊断，最终fence冻结后仅ledger1+旧public prefix7兼容1通过，2/2、147.93秒；不重复7绿，不重解释旧失败，冻结六路径交根审。
- 2026-10-24 04:00 +08:00：新增只读source_postcheck组件与7节点测试，首轮6绿1夹具失败完整保留；仅按根审把类型故障换到无trigger依赖的core_subjects.label，保留独立nullability及全部拒绝/不修复断言后只复验该节点1/1。原helper与6绿均未改/重跑；同JUnit实际SDK10→10/new0且setup已调用。四活节更新当前证据和未覆盖范围，3路径冻结交根审；新分支v4/p3-wire-source-forward-20261024自88f1d27延续，无git写入。
