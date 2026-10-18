# P3：接通可恢复的模型工具循环、人生线程与运行调度（开工）

本 ExecPlan 是活文档。Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective 四节必须随工作更新。格式依据仓库 `.agent/PLANS.md`。本文件为正式分支的实施计划；本轮只开工，不能作为整个P3完成证明。

## Context and Orientation（背景、源码定位与边界）

草案时间为 2026-10-18，Asia/Taipei。用户授权的 `15_Codex今日任务计划.md` 第6项只要求 P3 开工，允许完成多少记录多少，不要求本轮完成 P3。正式 P3 的全部验收仍列在本计划中，不因为本轮只开工而删去。

正式开工：2026-10-18 17:34 +08:00。分支 `v4/p3-agent-runtime`，工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，从已合并P1/P2的 `v4/main@b9a89b6f84f7bebb640de080548010859aae630c` 创建。P1合并 `7b45a781921e6fa2e875319a12af433f0cf505b4`；P2 PR #4 精确头1444a49通过全部CI 39114527541后合并为本基底。原P1分支和未运行的旧E1快照保留。P3保持草稿，不自行合并。

设计真相源为 `docs/v4/prompts/P3_Agent循环与工具.md`、`docs/v4/02_v4架构蓝图.md` §0/3/4/5/10/11/16、`docs/v4/06_明镜台系统提示词.md` 全文，重点为P1/P2/P8/P9。同步参考 `07_评测场景集.md`、`16_算命Agent架构研究.md` U4/U7、`AGENTS.md`、`.agent/PLANS.md`、`README.md`、`docs/CLOUD_DEVELOPMENT.md`。15号文件在大脑交付目录，未假定已复制入仓库。 v4.2叠加来源是`docs/v4/17_深度研究_算命Agent架构v2.md` §3/4/6、`docs/v4/prompts/supplements/00_索引.md` §3/4a/5、`P3_增补.md`全文和`19_新增评测场景.md`。功能区后续依据`22_功能区设计_对话与记忆分区.md`及`prompts/supplements/P5b_功能区与旧对话整理.md`，B部分才归主线。所有同步副本只复制、不改写；正式落盘须由root核对这些路径已存在及源文件SHA256。

下表依据已合并的P1/P2源码，行号仅作定位，以函数名与行为契约为准；实际调用方须在修改前完整阅读。

| 现有位置 | 复用内容与保留契约 |
| --- | --- |
| P1/P2 `mingjing_core/domain/consultation.py:85` `RuntimePort.execute` | 新运行时挂到已有端口，不把v3的LangGraph私有状态改成聊天正文。 |
| P2 `application/consultation.py:91,129` `submit/execute` | 稳定request_id、服务端owner、队列/租约入口；按runtime分流，v3路径保留。 |
| P1 `models/port.py:32,40,61,100` `ToolSpec/ChatMessage/AssistantMessage/ModelPort.stream` | 使用已规范化工具消息、工具循环reasoning与cancel_event；不另写供应商协议。 |
| P1 `models/registry.py:65,99,120` `resolve/port/RegistryPort.stream`；`models/schema_flatten.py:9` `flatten_schema` | 复用角色解析、已实现降级与schema扁平化；模型配置取合并后实际能力矩阵。 |
| P1 `repositories/postgres.py:177,379` `_operation/mutation_request` | 同operation_id同载荷可重放，异载荷冲突；不让模型提供owner、lease或operation_id。 |
| P1 `repositories/postgres.py:410,430,458,464,504,511,528` | queue/claim/renew/charge/dependencies/checkpoint/commit的既有权限与租约校验；新增v4分支，不整体放宽v3。 |
| P2 `repositories/migrations/0005_agent_runtime.sql` | 已有core_run_steps/core_run_events、runtime/lane/thread/cancel/deadline/usage列；建表不等于运行时已接线，不重写历史迁移。 |
| P2 `repositories/foundation.py:84,106` `thread_history/search`；`memory/tokenize.py` | 真实PG线程与中文FTS；搜索结果经过撤销投影，不绕开owner/subject/事项范围。 |
| P2 `application/memory.py:59,101,114,175,221,295,338,349,367` | receive、record_assistant_message、sources、save_fact、correct_fact、retire_fact、事项与snapshot；原话区间、显式授权和撤销继续由程序校验。 |
| P2 `memory/threads.py:26,37,115`；`memory/history.py:96` | UTC消息时间、稳定助手消息ID与血缘、撤销原话投影、历史分页；扩展无痕而非复制一个旁路存储。 |
| P2 `timekit/now_block.py:107` `render_now_block`；`calendar_cn.py:66,95`；`timekit/timestamps.py:7` | 此刻/假日/跨渠道历史瞬时解析；U4按来源消息的owner当地日期解释，不能按执行日期重算。 |
| P2 `memory/policy.py:18,59,63`；`repositories/privacy_foundation.py:62` | 不保存指令、假设/第三人判断与新派生层撤销闭包；步骤正文/事件需连入已建隐私传播。 |
| P1/P2 `application/consultation.py:450,460` `authorized_archive/_phase_calculation` | 仅抽出应用编排到charts_service供v3/v4共用，底层排盘与知识实现不改。 |
| P1 `adapters/tarot.py:112,239,245,288` `TarotService.create_draw/get_for_reading/begin_reading/finish_reading` | 实际塔罗服务在adapters，并非提示词所标application路径；固定牌面、揭牌、解释重试与所有权契约保持。 |
| P1 `adapters/web.py:271,293` 事项事件/资料确认；`adapters/channels/hermes.py:150` `validated_payload`；`adapters/delivery.py:45` `_fresh` | 从路由抽应用服务；core3/core4兼容需真实回读与投递freshness检查，不能只新增信封类。 |
| P1 `adapters/feishu_gateway.py:71,111` accept/_process；`adapters/web.py:126,136` worker/lifespan | 已有入站幂等与回收路径；取消网关直接consult，接同一dispatcher，保留显式渠道绑定和outbox不明不重发。 |

术语：运行（run）是一次持久任务；epoch是同一任务的重新生成批次；步骤日志是PG保存的模型/工具结果，完成步骤可以重放；回执是程序确认副作用的结果；人生线程是owner+subject的跨渠道对话；提交闸门是在发布回答前重新核对撤销与租约；信封是API交付回答及引用/回执的统一结构。脚本模型只替代模型或HTTP，不替代应用服务、工具或PG。

不可改变的v3不变量包括：owner来自认证/绑定，subject与第三人授权隔离；用户事实必须逐字溯源到有效用户消息，助手/工具不能转成用户事实；用户拒存优先、敏感确认、删除/更正传播、已撤销内容不复活；密钥不入库/日志/事件；outbox送达不明不自动重发；固定塔罗牌面不被解释重试改动；旧checkpoint只存ID；时钟经Clock注入，瞬时UTC存储、owner时区展示；Core/Charts两个环境隔离。新步骤中的reasoning只在受控PG用于同工具循环协议回传，不进入用户事件、公开日志、飞书或追踪。

保护目录：不改 `mingjing_core/adapters/charts/` 的算法/适配器、命理skills、`mingjing_core/knowledge/` 和 `web/` 前端源码，不开发P8技能、P5反思/向量、P6评审、P7发送、P9卡片或P10新界面。允许P3规定的后端 `adapters/web.py` 入队/取消/旧字段兼容接线与应用层charts_service抽取；不借此重写上述保护目录。排盘测试需要CHART_PYTHON，缺依赖必须记未验证。

## 最新用户决定与执行闸门（2026-10-18，覆盖旧默认值）

索引§4a与用户本聊天的明示决定优先于15号和增补正文中的旧默认值。D1继续全部使用Kimi Code会员端点（交互、评审、后台、评测、探针）；不自行切开放平台或更换User-Agent。所有会员调用归主线，P1b合并后统一走跨进程U38守卫，全局在途≤2，并按角色留额。`concurrency_limited`或`Access terminated`立即**全部停止**并置顶通知；不能沿用原表的“仅降到1后继续交互”行为。月额度/冻结持久全停，周额度置顶“线上可能受影响”，5小时额度停止并记录恢复时间。历史“到时自动续一次”不构成新授权：没有用户在线、在本聊天明确说“开始 E1 第 N 批”就不能执行或恢复E1；E2也须相应逐批开始。每批≤10个场景，目标/judge/probe/内部HTTP重试合计滚动5小时≤80，批间≥20分钟，夜间零任何真实模型请求（含探针）。原`--follow`无人值守协调器不再作为执行方式，不启动或恢复它。探针/等价性调用同样等用户明确说“开始”，授权不因完成一批而自动延续至下一批。

D2主模型和评审的目标配置都为`k3-256k`，primary/critic固定high思考且禁止关闭。切换前先由root在明确“开始”授权下跑≤20次等价性子集（P1b E5原8题×2模型≤16次可以满足），结论就绪后再启用真实目标；这不是现在可发探针的授权。代码/脚本可离线准备新配置，报告须标“等待等价性实测，尚未启用真实调用”。以后评测的被测目标也为`k3-256k`，不与P0`k3`基线相减；此前准备的`k3` E1清单/ledger身份不可静默改写，需root创建明确的新模型身份/新run并保留旧快照。新目标仍使用独立评审上下文。

D2附加上下文守卫必须在P3实现：目标约30,000 token，单次输入硬上限180,000，超过120,000先压缩较旧层，线程连续3次超过60,000在汇总提醒。完整对话仍存PG，不把全线程塞进请求；R07的300轮和10,000条合成消息都要真实PG装配验证上限与关键约束保留。每次调用的输入计量写账本，准确值/估算/上界必须分开，缺供应商usage记null，不能用字符串长度冒充真实token；具体计量与保守失败策略见M3a。

D4不开2小时使用提醒、不登记紧急联系人；上下文连续3次60k的汇总提醒仍执行，与使用时长提醒分开。P7只保留默认关闭的设置开关，本阶段不开发提醒或联系人登记/外联。危机兜底继续依设计模板，D4不删除安全支持。D5 E2只跑2025子集，由命理线准备脚本框架、root在用户在线逐批授权后执行；P3不扩展题集或发真实E2请求。索引D3的准确时辰与time_basis属于命理线，不挪入P3。

范围硬边界：不再写`zhiming-v4-p10`、`zhiming-v4-p8`、`web/**`、charts、skills、knowledge。模块线独占新增`timekit/relative_dates.py`（U4/parse_time_range）、`models/quota_guard.py`核心和`organize/**`；主线只按约定接口接线并做真实PG集成，不在这些文件创建第二实现。前端线独占P5b C；模块线独占P5b A。P1b修改models/配置/迁移/探针/评测守卫，P3修改agent及应用接线；跨分支接口要记录依赖，不能抄一份假guard或抢迁移编号。

## Purpose / Big Picture（目的与全局）

让模型根据当前消息与可核验证据，自己选择工具、观察工具结果后继续决定下一步，最终给出自由文本或一个明确问题。写入通过真实应用服务并返回回执，崩溃恢复后不重复写事实、跟进、抽牌或outbox。网页与飞书共用人生线程和持久队列，同线程串行，可取消，所有旧读取端仍显示回答。默认继续走v3；v4只在本机合成owner显式开启。用户看到的闭环是“发消息→模型真实请求工具→PG状态改变/返回→模型收到结果→回答入库→API回读”，不是某个工具类能单独调用。

## Progress（进度）

- [x] (2026-10-18 夜间) 队列9 B1离线候选：已有PG增量入口、Hermes wrapper同切方案、磁盘扩容/整理对照；28替身用例通过。工具默认只校验，实际Linux/备份恢复/解释器完整性与容量仍No-Go；未执行B，不改变固定b9候选。
- [x] (2026-10-18 夜间) 夜M2七工具应用/PG子切片：136项相关回归通过；真实MemoryService默认普通保存/敏感proposal/撤销、只读来源投影、持久scope与规范化参数指纹收口。见`evidence/P3/2026-10-19-first-tools.md`；U4解析与完整Loop仍未完成。
- [x] (2026-10-18 22:56 +08:00) 夜M3离线分层/D2子切片：层序、40/10窗口、有效派生血缘、实际注入依赖、TokenMeter阈值接口与真实PG持久streak已实现；证据`evidence/P3/2026-10-19-context-layers-d2.md`。未知会员framing仍拒绝真实发送，完整Loop/槽位/时间检索/无痕未接线，不勾完整M3。
- [x] (2026-10-18 22:04 +08:00) 夜间队列与边界已落盘：日报`daily/2026-10-19_main.md`、四线活汇总`daily/2026-10-19_summary.md`，本聊天30分钟续作至08:00。三个子任务按文件独占并行，root整合、测试、提交、推送，绝不访问服务器/真实模型/飞书/合并。
- [ ] 夜间M2/M3：第一批工具与完整上下文正在实施；夜间M4–M8顺序见日报，不把夜间编号与下方旧实施编号混作已完成。

- [x] (2026-10-18 16:22 +08:00) 在task工作目录完成设计与现有代码阅读，起草本计划；没有实现P3或建立分支。
- [x] (2026-10-18 17:34 +08:00) M0：P1/P2已合并；从`v4/main@b9a89b6f84f7bebb640de080548010859aae630c`创建正式分支并落盘计划，P2基线为553旧Core/615v4/208模型/80脚本+48自检。
- [ ] (2026-10-18 本轮) M1：Journal持久日志子范围已实现、真实PG39项通过；loop/工具执行/计费与依赖登记/安全提交/API回读尚未接线，不是完整M1完成。证据见`evidence/P3/2026-10-18-journal-slice.md`。
- [ ] M2 工具接线，优先U4/U7：未开始；后续按对应里程碑实现，不把首片原型当成已接线。
- [ ] (2026-10-18 18:02 +08:00) M3a：离线原型已实现并63项通过，真实PG 300轮/10,000条保留约束、压缩/拒绝/源投影通过；剩余可信供应商token计量、运行时接线和调用后持久提醒，不能报完整M3a完成。
- [ ] M3b 分层上下文、人生/无痕线程与v4.2缓存/检索接线：未开始；后续按对应里程碑实现，不把首片原型当成已接线。
- [ ] F1 P5b B后续里程碑：M3 ContextEngine完成后才开始实体/迁移/API/topic_route/分区上下文；A模块线、C前端线不在主线。
- [ ] M4 提交闸门、core4.0与读取端兼容：未开始；后续按对应里程碑实现，不把首片原型当成已接线。
- [ ] M5 调度、取消、网关与owner路由：未开始；后续按对应里程碑实现，不把首片原型当成已接线。
- [ ] M6 v4.2工具/澄清/危机/提示词补全和正式脚本、授权实测、stage计划与阶段回执：后续按本文扩展验证，本轮不承诺完成。
- [ ] M7 最后接入P1b U38守卫与体积错误恢复：依赖P1b合并，不用假守卫晋级。
- [x] (2026-10-18 本轮) 外部草案纳入v4.2增补、索引§4a决定、手动批次闸门和P5b B后续依赖；未实施。

## Surprises & Discoveries（意外发现）

B1首次安装工具不能用于现有PG增量。新增独立控制器分backup/migrate/backfill三道审查闸门，不调用freeze/install/publish，不开业务。Native目前只有替身证据，PATH二进制、候选venv完整性与完整owner覆盖须在任何实际B前核验，不能凭28绿解除No-Go。

首批工具只验证owner/subject不足：未选case消息、source_ids-only派生、profile聚合字段可能越过来源过滤；已补统一投影与8个PG边界。合法lease/step不等于本次参数匹配，原mutation_request仅防已有回执后换参；新增规范化参数+source_versions指纹在首次效果前核验，并将ctx.case_ids严格绑定持久run选择。

夜间分层回归发现通用mutation_request回执限定标识/状态，不应塞统计；D2改存run.usage的逐步骤元数据，thread只存计数与待汇总标志，Journal完成后的usage保持不可变，避免重放complete冲突。超长181k无标点同字输入阻塞既有jieba入库，强停仅本次测试，记录性能未验证并切换自然分句同长度上下文边界用例；不改旧断言掩盖问题。

夜间用户队列从M2开始，但现有Journal仍未接AgentLoop，实际循环是后续工具/E2E的依赖；root将补最小循环并以真实PG验证，不假称白天已经接通。模块树22:02出现，需只读收集其日期/组织模块交付并避免双写；夜间U38核心由用户明确分给主线，若发现同名并行文件则停该文件切其他项。

授权A实证：生产是7dbc951/Core v3与schema4，两库校验和与b9前缀一致；rootfs仅余0.737GiB，Hermes Core wrapper也固定旧包。B1已形成`release/B1_operation_sheet.md`，先交大脑审、再申请B，不能只改systemd就宣布完整增量切换。23号已裁定B1保留实际k3，新模型等价在P1b后另做。没有执行部署/备份/模型调用。

Journal中Python的True与1相等会误认回执幂等，已按JSON类型区分并增加回归。来源撤销可清空completed的output；重放必须拒绝，不能根据completed状态重建正文。工具输入指纹仍须由未来loop纳入有效来源版本，Journal自身不代替依赖登记。

首片实证：共享facts helper默认硬limit=10000、撤销helper取整个owner，因此新增有界目录探测与默认256事实/512撤销的保守支持域，超限拒绝而不丢约束；fact_limit不能设置超过10000。历史限定最新用户源时点；同事务双时间戳顺序不明则拒绝，不拿随机ID假装真实先后。

独立review发现并修复重复span遮盖、后到消息混入、未知envelope摘要丢回执与mixed tool_cycle丢推理；63项目标测试覆盖这些边界。无模型网络，PG真实，原文保持原字节。candidate_counts是受控候选集/缓存基数，不等于全部内部SQL返回行数。

当前计量是完整规范化JSON UTF-8的policy_units，并非会员token或最终供应商HTTP字节。actual_input_tokens/input_token_upper_bound为null，live准入始终失败关闭；这不是供应商180k token/缓存命中已验收的证据。公开K3词表研究不能替代会员framing合同。

P2迁移0005已经准备运行表，0006/0007提供线程索引与FTS，但当前业务仍用线性LangGraph。不能再报“加表/加类即Agent完成”。P2 `record_assistant`明确只接受`life:<subject>`，无痕线程需要在同一来源/撤销契约下扩展；否则即使ContextEngine接受incognito，最终助手消息仍无法落库。

P2 `save_fact`仍把preference/constraint以外种类视为敏感，需要确认；P3的M01 event/M02 goal自动记忆必须通过蓝图§6.2分类落实，不能只在tool wrapper把pending改成saved。相对日期目前没有可靠的统一写入路径，因此U4要同时改memory_write与schedule_followup，并验证PG里的真实结果。

现有web worker单并发轮询，飞书accept已持久入站但_process仍直接consult。仅增加dispatcher文件不会改变这些入口，M5必须替换调用。`pg_advisory_xact_lock`只在事务内有效，不能释放短事务后声称仍保持线程串行，也不能把8分钟模型流包在持有owner锁的长事务里阻塞取消/续租；需在短事务的线程锁下核对并领取持久线程租约，由实际PG竞争测试证明。

C21/E1冻结逻辑主动拒绝P2源码。P3基于P2，不能调用其旧v3冻结入口来评测v4，不能修改该拒绝来迁就新代码。新v4 target与报告必须独立；旧P1 k3快照仅保留历史、未运行；后续E1需要pre-P2旧业务加经过审查的P1b兼容桥，另建k3-256k身份/manifest后仍等用户逐批开始。

## Decision Log（决策记录）

2026-10-18 夜间 / Codex：B1增量控制器作为固定b9包外的独立受审工具，以源码合集hash绑定审批；backup→隔离恢复proof→迁移7与授权→dry-run审查→apply两次与retarget，始终保持全部writer停写，真实发布另获授权。不增加tzdata到B1；磁盘两方案只文档，明天用户裁定。

2026-10-18 夜间 / Codex：首批工具以真实PG子切片单独发布，U4缺模块交付不等同无歧义；不造第二词表、不把注入Parser的接线测试当语言准确率。ToolRegistry.fingerprint补Pydantic默认后生成持久指纹，应用层再次校验；首轮和重放同一规则。工具扩展与无痕提问将区分只读/允许临时线程写，D4只关闭使用时长提醒，不关闭用户明确set_reminder。

2026-10-18 22:56 / Codex：D2的estimated、上界、provider actual分别记账；>120k才按token上界压缩，180k不得配置抬高。synthetic meter只用于离线阈值证明，无法使live_admissible为真。上界/实际连续计数分开，第三次触发一次且持久pending，模型步骤键防重放重复计数。不为缺失计量/模块日期词表发探针或另造词表。

2026-10-18 22:04 / 用户夜间明确授权：按队列夜M2第一批工具→夜M3完整ContextEngine→夜M4第二批工具→夜M5线程/inbox/飞书合并→夜M6闸门/core4/U41→夜M7dispatcher→夜M8脚本v4；之后P1b离线与B1本地增量及加分项。每小时日志，每里程碑测试/提交/推送/小回执，08:00前四线汇总；不等睡觉用户，阻塞记待决后立即换项。今晚的禁止服务器/真实模型/飞书/主干合并覆盖早前授权A继续访问许可；不重复读取线上。B1固定b9、tzdata随B2、磁盘明日决定，生产草案明确Hermes wrapper同切。

2026-10-18 / 用户授权A及23号：仅服务器只读盘点已执行；无需口令、新建登录或写配置。未来stage/生产仍分别授权，当前继续本地P3/P1b。用户本轮明确允许主线改Charts锁，故仅增加tzdata2026.5和独立双系统包数据检查，不改排盘算法/命理目录；该修复不混进固定b9发布包，候选差异交大脑裁定。

2026-10-18 / Codex：M1先提交有真实MemoryService/mutation_request恢复证据的Journal原语：短事务、当前lease/epoch/scope/cancel/deadline校验、稳定操作号、失效正文拒绝重放。没有真实模型或工具循环接线，不补假Toolkit来冒充闭环。新建执行/重新领取lease/外层事务回滚后均重新创建Journal遍历。

2026-10-18 / Codex：先交可独立验证的离线上下文切片，新增context_sources.py拆开真实PG取数，遵守≤400行/函数≤60；不改共享MemoryService/旧runtime，不占模块线新模块。三项字段estimated/upper_bound/actual不混用，未知供应商投影拒绝live，不用任意padding常数伪造保证。单工具9k策略单位但总量<30k时尚无预压缩，正式8k token守卫留后续。

2026-10-18 / Codex：B1计划固定P1/P2合并b9a89b6，只准备stage/生产执行单、备份/恢复和授权清单；没有访问服务器、执行迁移/回填/服务命令。B1方案不把P3/P1b/P5b/P8/P10混进发布包。

2026-10-18 / 用户与大脑增补：**P3增补v4.2已纳入**。D1/D2/D4/D5按索引§4a执行；它们覆盖增补P1b§G的“默认不启用/等待决定”以及旧自动续跑许可。P3/P1b真实请求均等待本聊天明确开始；本次草案没有请求。ContextEngine守卫作为M3a首先实现，可与M1日志闭环并行离线验证。原有U4/U7不删除，U4模块线实现、主线接线。

2026-10-18 / P5b B拟选技术方案：保留`case`与`topic`双向关联（选项b），理由是已存在的`/api/cases*`、事件/修订、原话引用和塔罗case链路均有真实兼容契约；先加关联可减少迁移与回滚风险。此为拟选，正式F1启动时核查P5实际schema后记录最终决定，不把此草案当已实施。F1只做B；A、C不进入主线。迁移排0009之后，**待P5协调具体编号**，不得抢用0008/0009/0010/0011（分别为model_usage、memory_proactive、pgvector、retire_langgraph），也不先创建空迁移占号。

2026-10-18 / 计量真实性：Core锁无已安装Kimi tokenizer；官方公开K3词表与XTML encoder已有固定版本只读证据，但会员服务端framing等价仍缺证明。采用独立TokenMeter接口并在计量报告标`source/model/version/is_upper_bound`；没有可证明覆盖最终请求全部组件的计数/上界时，真实发送守卫失败关闭，脚本/PG压力测试继续。UTF-8字节数可作保守裁剪单位，但仅在计量器具备已核验byte-fallback及framing上界契约时才称token上界；否则标policy_units，不发布“实际token≤180k”结论。最终供应商usage另记actual_input_tokens，绝不回填为估算值。

2026-10-18 / 缓存矛盾待大脑：增补G要求L5块内每轮追加，同时要求两轮前五层（含L5）整体逐字节一致；新消息追加会改变完整L5。先以不改写既有L5字节、稳定层/旧窗口前缀字节相同验证缓存友好性质，并在未决问题保留“整块相同”字面验收，不能自行宣布该项通过。工具固定顺序/按状态可见优先，不按话题换组，≤15工具上限仍执行。


2026-10-18 / Codex草案：实施顺序为最小闭环→工具（U4/U7优先）→上下文线程→闸门/信封→调度路由→全面验收。理由是每步都接真实路径，先证明模型看到工具结果再继续，避免交一堆未接线模块。无需改变设计意图；正式基底由root核实后采用。

2026-10-18 / 用户15号任务与root边界：本次只开工，P3保持草稿，不合并、不stage、不访问生产、不发真实飞书。P1新端口全局开关在E1结束前默认off；本机P3通过依赖注入使用P1 ModelPort与脚本模型，不切换生产配置。所有真实POST只能由root统一发起，沿用同一个会员账本、真实HTTP记账和停止规则，子任务不得自行probe或live。

2026-10-18 / 契约隔离：07附录B是v2.2数据定义，不能加入今日v2.1基线或更改旧80场景/rubric。U4/U7先以真实PG集成用例验证，TM01/TM02/AX02作为对照场景；只有root完成v2.2父契约绑定与执行接口冻结后才发布该版本成绩，不称现有12个定义为已验证的92场景契约。

2026-10-18 / 范围决定：chart_skill在P8；consult_specialist可留P8，正式回执写清未实现与理由，不静默把独立专家分析假装普通工具。P3只做未知别名移除/告警与空回答兜底；不调用v3 `_validate`、不提前启用P6 critic/legacy lint。撤销触发的一次重新生成属于提交安全，不是任意风格评审。

## Outcomes & Retrospective（结果与复盘）

队列9离线候选已形成，运行说明、验证和磁盘方案在release/B1_incremental_*.md/B1_disk_options.md；只证明替身控制流，实际主机/PG/恢复能力保持未验证，不作执行授权。

夜间已有七工具应用/PG与分层/D2离线子切片，正式测试与提交回执见夜间日报；完整M2/M3和P3仍在推进。白天证据保留，不用已有39/102/382和双系统CI冒充新源码验证。最终汇总提前建立，逐小时更新至08:00前，未覆盖项必须逐一如实标注。

本轮续作：Journal子范围39/39真实PG通过，合并复核agent目录102/102通过（70.81s），Ruff/格式通过，无新增迁移；使用现有0005表，实际工具崩溃窗口和已登记依赖撤销已验证。Charts tzdata锁和Windows本机21边界/5项回归通过，Windows/Linux Actions39119854074均success；B1授权A完成，只读操作单已交审。P3/P1b均保持Draft，无合并、stage部署、真实模型或消息。

本轮完成P3开工与M3a离线原型：代码本机97f656cd177d573a0eb9c11a668ea0d13a40881d，等价远端代码e9ad78b98e61a3d48e11253b7670f52701a8adff，PR #8保持草稿。本轮63目标测试、R07真实PG300轮/600消息与10000消息压力已通过，工具/推理完整字段预算、源span/revision与scope、压缩和required拒绝、原文不变均有证据。scripted原80/80和48自检通过；全v4 678/678（208.35秒、零skip）通过；最终新代码CI待发布后核验，不作为完整阶段完成。

未完成完整P3：loop/Journal接线/dispatcher/core4提交与读取端、U4/U7、无痕/时间检索、缓存分块、澄清/工具集、实际token、用量账本、3×60k持久提醒、P1b守卫和真实质量。F1/P5b B仍严格等完整M3完成，A/C不归主线；没有迁移/新API或任何真实调用。默认v3未接入本原型。

## Plan of Work（工作计划）

### M0：确认合并基底、环境与测试边界

root确认P1CI绿并合并、P2 rebase/锁文件和完整组合回归通过并合并后，从该`v4/main`建立P3 worktree，记录精确SHA、工作区状态和提示词版本。复制本草案为 `docs/v4/execplans/P3_agent_runtime.md` 前重新核实复用函数与迁移号。

读取现有本机PG管理说明，使用明确的可丢弃本机P3库及独立测试schema，不与E1的`core_test_e1`共库，也不清空主线或他人测试schema。DSN只通过进程环境引用，报告不含凭据。迁移用已有独立migration role，运行角色不得被临时授予DDL特权。Core依赖使用合并后的精确锁；不升级、不混装Charts环境。

保留旧553/Core测试、已有v4测试、旧80脚本作为回归基线；本轮fixture修复只能隔离单测ROOT，保留“未跟踪源码不能冻结”和“P2不能用于E1”的断言，不删测试。M0的真实PG检查包括连接/版本/迁移校验/owner隔离；结果入证据，未配置PG时不能把skip当通过。

### M1：步骤日志与模型→工具→模型→提交的最小闭环

建立 `agent/loop.py`、`journal.py`、`toolkit.py` 和 `tests/v4/agent/`；通过 `RuntimePort.execute(service, owner, run_id, lease_token, emit)`接入可注入的新运行时。此时只对合成本机调用显式注入，不改变默认v3路由。最小上下文使用真实system、本轮有效用户消息与P2此刻，M3之前不宣称分层上下文完成。

Journal实现 `next_or_replay(run, kind, name, input_fp)` 与 `complete(step, output, usage)`。验证owner/run/epoch/lease、稳定seq和输入指纹；完成步骤读回，未完成模型步骤可重发，未完成工具步骤用相同 `run:{run_id}:e{epoch}:s{seq}` 执行。工具副作用与receipt都经应用服务/`mutation_request`幂等；一次写入已成功但步骤complete前崩溃的窗口必须覆盖。异载荷重用operation_id报冲突，不能猜测重放成功。

先接 `time_context`、`memory_search`、`ask_user` 与一个真实可写的非敏感memory_write路径。脚本ModelPort按实际 messages 输出“查时间/写记忆”的ToolCall，再断言下一次请求含对应tool_call_id、工具结果和saved/pending真实回执后输出文本；不能直接回放期望数据库状态。所有同次只读工具可线程池并发，写工具顺序执行，读写依赖不满足时不得并行；工具异常是安全的ToolResult，不伪造成功。未知/不可见工具、无效参数、重复call_id有确定性失败结果并记日志。

使用 `ModelPort.stream`聚合规范化AssistantMessage，保留同工具循环需要的reasoning/signature/tool_cycle；定义 `emit(type, data)`默认安全no-op，P4才做前端事件传输。迭代/墙钟/每轮工具上限从`config/runtime.yaml`读取：interactive40/8分钟/6，background60/20分钟/10；同名同规范参数第3次熔断。v4调用只记usage与账本，跳过v3 CALL_LIMITS/repair门；v3限制不变。会员80次是额外的共享供应商保护，不能因v4业务取消CALL_LIMITS而取消它。

`ask_user`以ends_turn结束当前run，asked包含question/options/allow_free_text/why；无interrupt/resume，新用户消息创建下一轮。没有最终文本时生成简短中文说明并保留已完成工作/回执，不能空返回。prepare_context以规则和首轮安全判断进入危机模式，叠加crisis提示，只暴露time_context/memory_search；热线来自crisis.yaml，不暴露命理/塔罗，正反例各至少15条。

M1独立证明：真实PG中提交→claim→脚本ModelPort→应用工具→后续模型请求→回答/步骤/回执回读；恢复时同run/epoch完成工具不再调用，事实和mutation行各一份。对已接副作用工具分别在执行前、效果成功后日志完成前、完成后抛SystemExit，过期/重新claim后继续。模型完成日志重放不得再消耗脚本调用。最小提交桥必须提前实现M4所需的基础v4安全校验（owner/lease/epoch/取消/本轮写入识别/依赖撤销），并在M4扩展一次重生与全部读取端；不能把结果伪装成validated core3.0来绕过旧commit_run。若该桥尚未接好，M1只记为内部模型工具循环原型，晋级条件是经过安全提交并由API回读，不能宣称用户对话闭环或完整P3验收。

### M2：全部第一批工具接线，优先U4/U7

每个Tool定义name、06 P9中文description、Pydantic参数、经P1 flatten_schema输出的ToolSpec、visible(ctx)、execute(args,ctx)与ToolResult `{ok,data,receipt?,ends_turn?,summary}`。summary只含类型、数量、状态，不含原话或reasoning。参数Schema不接受owner/operation_id/lease；执行层也重新验证权限与可见性，不能只隐藏工具列表。每次发模型的工具集合≤15，只按资料确认/塔罗/无痕/危机等少数状态变化工具可见性、固定注册顺序，不按话题换组；危机/无痕限制优先；不因工具总数超过15而任意截断掉本轮必要能力。

| 工具组 | 应用层接线与可观察结果 |
| --- | --- |
| time_context、calendar_lookup | 调用P2 timekit/节假日覆盖/owner Clock，区间查询加入本人事件；未知年份显示未公布，不对话联网。 |
| memory_search | 同ContextEngine的FTS实现，支持kinds/since/until/limit，带来源日期和run别名；不得返回跨owner或已撤销范围。 |
| memory_write、memory_update、memory_forget | 复用save_fact/correct_fact/retire_fact，U4归一化；用户原话区间在代码校验；分类与proposal按§6.2落实，pending不能说saved。 |
| note_write | 写inferred=true与source_ids，推测不升级为用户事实，不授予出生资料授权。 |
| profile_get、profile_update_request | 读取有效授权资料；写请求只产生确认请求/proposal及回执，真正更新仍经现有profile/confirm显式确认与revision。 |
| chart_compute | 提取authorized_archive与计算编排到application/charts_service.py，v3/v4共用；无已确认资料不可见且执行拒绝；返回现有claim与公开错误/缺口，不复制算法。 |
| tarot_start、tarot_read | 复用TarotService、揭牌前不读；读取固定draw并开始/完成解释，解释失败重试同draw；加入U7而不删原有身份/previous_draw校验。 |
| case_list、case_update、case_add_event | 把web嵌套的事项更新/事件逻辑抽到应用服务；保留expected_revision、原消息和source_refs；工具与HTTP共用。 |
| ask_user、present_options | 前者ends_turn且每轮最多一次；后者≥2个选项，含收益/代价/风险/可逆性/第一步，未知值待确认；不直接改变现实决策。 |
| schedule_followup、set_reminder | 仅写实体（due_at/topic/reason/source_fact_id/status=active）；重复重放只一行，实际发送在P7，本阶段不调用飞书。 |

记忆分类按§6.2取规则与模型自报的较严结果：工作/学习/目标/事件等非敏感信息自动保存；身心健康、他人隐私、具体金额/债务、性取向/宗教/政治、法律纠纷生成proposal，出生资料仍走单独确认。拒存规则正反例各至少15条，保留“别忘了记住”等非拒存回归；M05–M08作隐私与确认补充集成检查，不能通过改旧测试绕过。P3允许proposal先落实体并回pending_confirmation，确认UI留后阶段；不得伪造按钮已接通或auto_save_categories已由UI写入。

U4接入模块线提供的共用确定性日期解析服务`timekit/relative_dates.py`；主线不写该模块或重复词表，输入为有效原消息文字、消息said_at瞬时、owner时区与可选确认，输出resolved/needs_confirmation及绝对event_at、said_at、原始说法与解释基准。即使模型给event_at，也不能跳过原话核验与程序换算。日期值为`YYYY-MM-DD`时保留纯日期，不擅造午夜；用户给具体时分才按当地时区解释后存UTC。said_at核同一瞬时，不强制保存`+08:00`原字符串；quote与原始相对说法逐字保留。重启/延迟执行仍用消息时刻，不用重跑当日。

U4正反例各≥20：基准2026-10-17周六，覆盖下周三10/21、过两天10/19、月底10/31、跨月/跨年、闰年、owner跨时区与具体时分；反例含周日“下周三”歧义、缺消息时间/时区、多个冲突候选、无效日期、不可确定“改天”、否定/假设语句、助手/外部来源与已撤销原话。歧义返回needs_confirmation，不能持久化猜测event_at/跟进；下一轮ask_user确认用新用户消息锚定。真实PG两轮从10/15原话写入开始，10/17查到10/21且还有4天（TM01）；9/30“月底交房租”到10/17仍指9月底，不臆测已缴（TM02）。

U7按owner+subject、规范化/高度相似的问题、实际elapsed24小时查recent draw；不能用换session/渠道/新case绕过同一问题，也不能把不同owner牌面返回。规范化和相似度使用可测试的本地有限规则，保存版本；首版阈值及边界用例在DecisionLog说明，避免用模型自主判断是否绕过。命中时零新draw，返回recent_draw_exists/旧ID，模型先引导回看或补充背景。只有新的用户原话/显式用户动作确认坚持，才调用既有explicit_new/previous_draw_id路径；模型单独填true不能充当用户坚持证据。旧牌、牌序、朝向、揭示与解释记录保持原样。

U7真实PG测试包含1小时内相同/同义问题护栏、跨session/channel/case、23:59与24小时边界、明确坚持后的唯一新draw、异owner/subject拒绝、并发重抽、旧牌不变与解释失败重试不重抽（TA01–03、AX02）。每种新增写工具补M1同样的崩溃窗口/重放测试；只读、参数、可见性测试也必须通过实际Toolkit分发，不只直接调类方法。

### M3a：ContextEngine先实现计量与硬上限（可独立验证的首个切片）

从真实P2 `MemoryService`读取当前owner/subject的有效事实与经过撤销投影的线程/FTS结果，建立`agent/context.py`纯装配入口及小文件`context_budget.py`、`context_types.py`，单文件≤400行。不要为了压力测试一次性调用`repo.list(...limit=100000)`把全部正文载入内存，也不复用会扫描全部历史的UI `history_window`做每次模型上下文；窗口查询按thread/index有界，关键约束单独读有效事实。所有只读查询保持owner/subject/事项授权及source_span投影。万条完整历史仍在PG，装配只读取预算所需窗口与Top-K。

`ContextEngine.build(run)`第一版返回Layer集合、规范化messages、alias_map、injected_sources、MeterResult及裁剪轨迹。每层区分required（L0政策、有效全局约束、L1此刻、L6当前用户原话与本运行尚需的tool-call配对）与compressible（旧L5、L4低排名、L3非关键细节）；输入计量涵盖**工具schemas、system/persona、L2/L3/L4/L5/L1/L6、全部同epoch助手reasoning/signature、tool_calls与工具结果及供应商framing**，不能只数content。工具结果替换保持call_id/角色配对，不能截坏JSON/UTF-8或丢掉本轮写入回执。当前用户消息或关键约束自身大于硬上限时返回明确`context_required_overflow`，不截断约束、不发POST；后续交付安全中文说明，测试验证调用次数0。

阈值默认target=30,000、compress_above=120,000、hard_max=180,000、large_tool=8,000，均从配置读取并校验顺序。先按各层预算争取30k；每轮装配后检查最终请求估算/可信上界，超过120k立即按旧L5前移→L4降K→大工具结果summary+alias顺序压缩，循环必须每步减少预算并有最大次数，压缩后再计量；仍超过180k阻止发送。规则产生的摘要只说明消息数/时间段及“更早的对话见检索”，不能凭空用模型写摘要或将未读取历史编成事实。P5已有有效摘要时才引用该摘要与来源，撤销后不得重放。

TokenMeter区分三种产物：本地估计`estimated_input_tokens`、有依据的保守上界`input_token_upper_bound`、供应商成功返回的`actual_input_tokens`。估算不作为硬上限证明。可以首先实现与标注tokenizer配套的本地计量器和字节策略计量器用于脚本/PG压力，但Kimi分词器与协议framing上界未确认时**真实发送不可声称安全**，必须由发送前可信meter拒绝未知计量；不得为了能跑而把bytes/4记作token。若官方本地tokenizer可直接从已锁依赖复用，记录版本/hash与覆盖字段；若需要新依赖先在root统一锁文件后接入，不在本任务升级环境。严格180k门控应在每次端口调用前重复执行，以包含循环里新增reasoning/工具结果，而非仅prepare_context一次。

每次调用准备记录输入计量与thread/run/epoch/step/model/meter_version及压缩前后层大小（不含正文）。P1b合并前保存在既有`core_run_steps.usage`/run usage中；P1b接线后写其`core_model_usage`实际usage与可选计量元数据，schema变更由P1b统一，P3不抢0008。供应商不返usage或失败时实际输入保持null，不能用0代替未知；即使有usage也不能倒推未发请求。线程连续3个实际请求超过60k生成一次持久安全汇总标记，下一个≤60k重置；只有可信预估而无actual时另标“计量超阈值”，不能混成actual提醒。使用步骤唯一键去重，不因journal重放重复推进计数，重启后延续。如何在同一条账本列保留provider值与preflight上界需要P1b接口确认，不能误覆盖actual。

独立证据：使用真实隔离PG写入R07 300轮（600用户/助手消息）和单人生线程10,000条消息，首轮写入不少于3条远处有效约束（如不能上夜班、花生过敏、周末照护）及不同位置的事件；真实MemoryService/ContextEngine每轮装配，断言每次可信计量/上界≤180k、约束原文与来源别名持续在场、最新问题完整、撤销约束不再注入、其他owner和无痕不漏。长中文、ASCII、emoji、combining text、巨型tool schema/8k结果、120k/180k边界、超大单条required分别覆盖；至少一个压力输入先超过120k并观察真实压缩轨迹，不能只测天然小输入。持久线程消息总数/原文字节哈希前后不变，说明压缩只改变模型装配。脚本ModelPort记录最终请求及meter元数据用于离线断言，实际模型调用0。该切片通过只证明计量/装配/PG约束，不代表检索质量、完整循环、P3或真实Kimi token验收完成；无可信meter时上界项明确未验证。

### M3b：v4.2分层上下文、缓存、时间检索与人生/无痕线程

工具定义固定注册顺序，工具可见性只随资料确认/塔罗/无痕/危机等状态变化、不按话题轮换；然后按L0→L2→L3稳定→L5→L4→L3易变→L1→L6装配。system初始逐字取06 P1，onboarding/crisis逐字取P2/P8；在M6§H逐字叠加后system升v1.1.0并写run meta/hash。P5前L2有效事实按类别分组、约束始终置顶；L3稳定含未结事项标题/目标/最近3事件、命盘/档案已有摘要；易变含≤5未过期澄清槽、知识缺口Top5/待跟进，缺少数据就省略，不造摘要。

L5采用分块推进，默认原文30轮，超过40轮起点前移10轮；块内只追加、不改写既有字节。预算提前前移记录原因。P5前没有有效摘要时写“更早的对话见检索”，不得自动发模型压缩。稳定工具定义到L3稳定应逐字节一致；L5既有前缀一致和窗口前移变化另测，增补要求整个前五层一致的冲突保持待决。run usage保留cache_read_tokens/cache_write_tokens（缺失null），报告统计多轮缓存命中率而不设虚假门槛。

L4与memory_search共用P2 FTS应用入口，查询含本轮+最近2轮及有限可解释的指代展开。先调用模块线`parse_time_range(text, now, tz)`：可信区间按since/until检索，再无过滤补足K、去重、时间命中优先；不识别/低置信则不过滤。块头显式time_filter。当前P2 foundation.search过滤created_at而不是event_at；TR01所需事件时刻语义必须在应用/查询接线明确区分，不能把入库时间当事件时间。P5再扩展双时间/向量，主线不写parse_time_range词表或timekit模块。TR01–TR03脚本证明具体节日/日期而非只测解析器。

L4每条一行固定JSON `{alias,date,kind,source,valid,text}`，source明确用户渠道或“明镜（我之前说的）”，P5前valid恒true仅对有效投影条目；已删除/撤销不作为valid=false装入。助手话语当前为消息原文检索，P5才做assistant_claim。f/n/e/c/m及未来r别名只绑定实际有效、同scope数据；finalize未知别名移除并告警，合法引用进used_*和来源血缘。L1复用render_now_block，上一条用户消息取真实线程时间、未来7天按event_at/跟进。

主线程life:<subject>跨网页/飞书，原始消息含UTC at/channel/kind/topic_id；session_id只作topic标签。record_assistant_message和history_window复用但作core4兼容。inbox在迭代边界按持久消费状态注入，不吞、不双用。无痕经显式用户语句/incognito参数建立经认证的incognito:<uuid>，owner/subject绑定、24小时无活动到期；扩展P2线程服务时仍保持来源、撤销与revision。无痕不写长期实体、不进主线程FTS/画像/反思。消息中的“结束无痕”退出；附件仅视为未验证。

真实PG验证M13、R01–R09、Q01–Q07、T10/T14、TR01–03：跨session接续助手B方案、远处关键约束、空owner拒绝编造、过时日期不漂移、无痕正文前后不可在主线程/FTS/派生层找到。M3a压力用例持续运行并绑定最终序列化请求。P2 backfill只用合成数据验证幂等/撤销，不迁移真实历史。只有M3的这些装配/预算/线程证据完成后，F1才可开始。

### F1：P5b B后续里程碑（严格依赖M3完成）

只实现B的space/topic实体、标签字段/索引、幂等revision API、topic_route及分区ContextEngine；不实现A切段/分类/聚类/建议纯模块、不实现C界面。依赖模块线按公开接口交付，缺模块不写替身冒充应用整理。拟选保留case与topic双向关联并保证旧/api/cases*兼容，最终DecisionLog在P5迁移协调时确认。新增迁移排0009之后但具体号待P5协调，保留0008/9/10/11归属。

owner首次使用幂等创建7默认区。space包含id/name/description/sensitive/order/hidden/revision；topic包含id/space_id/title/status(open/archived/case)/summary/summary_until_message_id/case_goal/created_at/last_at，14天无新消息归档并保留摘要。消息/事实/笔记/情景/draw新增space_id/topic_id/space_secondary/route_source/route_confidence；route_source限rule/embedding/model/user/migration，只增字段/索引，不改原正文。新增消息表达式索引(owner,space_id,topic_id,at_ms)，具体迁移编号仍等协调。

API包括GET/POST/PATCH /api/spaces、GET /api/spaces/{id}/topics、PATCH /api/topics/{id}、POST /api/messages/{id}/route、GET /api/organize/proposal、POST /api/organize/apply {batch_id,edits[]}、POST /api/organize/revert {batch_id}；所有写操作遵守request_id+expected_revision。变更集应用/撤销原子、并发冲突不覆盖新修订、跨owner拒绝。工具签名为topic_route(space_id,topic_id|"new",title?)，每轮可见但仍占≤15工具预算，改本轮用户消息归属并发route_changed，P4事件协议小版本升级需协调。

路由写入校验同owner/subject及topic所属space；topic_route绑定当前run/source/lease与稳定operation_id，只改归属标签，不改原正文或时间；其合法revision推进计入本轮依赖，避免将本轮归区误判为外部stale。

A/C交接只消费模块线的RouteDecision及含逆操作的ChangeSet和版本，不改organize/**。向前端线交付API schema、幂等/修订冲突错误与route_changed协议小版本，不实现界面。space.sensitive及服务端敏感内容投影仍由主线在P7/P9负责，C只负责展示；F1先测敏感标记和API隔离，真实推送留后阶段。

apply/revert只恢复该batch拥有且revision未变的标签/关联；已删除或撤销的来源不得由inverse或旧proposal复活，topic摘要、跨区摘要与ChangeSet均按来源血缘失效。

分区上下文按22§4：L2当前区细节/其他区一句话；L3当前区话题事项完整/他区标题；L5当前话题最近30轮+当前区有效摘要+他区最近7天一两句；L4当前区×1.5但其他区可召回，**约束全局置顶**。跨区召回和全局约束仅限当前已授权subject/thread，无痕正文不进入跨区摘要；身心/财务内容的敏感性不得因模型改区而解除。M3a180k/120k/3×60k/30k约束继续生效。P5沉思尚未上线时他区近况只显示已有可信摘要/安全缺省，不为凑字段发请求；未来每天一次更新，D1仍生效。撤销覆盖topic摘要、他区摘要、ChangeSet。SP01–SP04/SP06/隐私后端测试用真实PG，SP05卡片属P9；SP07界面展示归前端，锁屏正文脱敏的服务端投影与后端测试由主线P7/P9负责，改区标签不得解除脱敏。stage副本旧对话整理/正式apply均属于P5b E且在B2之后逐次授权，本轮不执行。

### M4：提交闸门、core4.0与全部读取端

为v4建立明确的envelope Pydantic契约：schema=core4.0、message_id/text/receipts/used_fact_ids/used_claim_ids/asked/review/usage，保留run/runtime/prompt/model元数据。与现有core3.0字段schema_version/answer/validation的桥接必须显式，不只接受一个schema字符串。v4自由文本不经过v3 _validate；只有别名、空回答和撤销提交安全检查，P6质量评审不提前接入。

在repository应用边界新增v4 commit路径，继续验证owner/lease/epoch/已取消状态。按服务端注入的run:{id}:操作前缀识别本轮自写，不把自己的合法memory_write当外部过时；跟踪实际注入与引用的事实/消息及撤销水位。无关外部修改不误判；本轮依赖被撤销则重建有效上下文、最多一次新的生成epoch，旧副作用按既有operation/idempotency保留且不复活撤销。第二次仍受污染时交付不含已撤销依据的安全非空结果/明确说明，不无限重跑或静默丢回答。每次实际再生成仍计共享模型预算。

助手消息入库与最终run提交使用可恢复且一致的应用事务/幂等协议，避免出现“回答可见但run没完成”或崩溃后双份消息。P2助手消息默认assistant:前缀若参与v4写版本识别，要在v4调用时注入受信run操作标识；不全局忽略其他助手消息修订。

修改所有读取端的兼容投影：channels/hermes.validated_payload、delivery._fresh、tarot.finish_reading、GET /api/chat/{id}、GET /api/runs/{id}、GET /api/history；旧前端看到answer映射text且仍可读历史core3.0。outbox只按已提交新信封构造，失鲜/撤销拒投，送达不明不重发。

M4真实PG用例同时覆盖自写不stale、外部无关写不误停、注入事实撤销、原话区间撤销、一次重生、再次污染、失效token/跨owner提交、崩溃后单助手消息/单outbox。分别把core3.0/core4.0通过真实API和mock渠道读取，检查记录与projection相同。旧DOM读取测试必须验证v4完整一轮显示，不能仅断言JSON包含text。

### M5：dispatcher、取消、飞书合并和owner运行时路由

实现AgentDispatcher并从FastAPI lifespan启动/停止，替换现有web单并发worker，web与飞书都只写入站/入队。interactive/background两通道，全局并发默认CORE_RUN_CONCURRENCY=3，interactive有可获得的容量，后台不占满所有槽导致对话等待完整20分钟。使用短事务中的线程advisory_xact_lock与持久claim状态保证同线程互斥；真正同线程键包含owner/subject，避免不同owner的life:self互相串行。多连接/多dispatcher测试证明全局上限与串行，不能只靠进程字典锁。

LISTEN mj_run_queued唤醒、NOTIFY入队、2秒轮询兜底；LISTEN连接断开可恢复，不靠模型探针。租约150秒，步骤间与流式每20秒续租，模型I/O期间不持owner事务。取消路由POST /api/runs/{id}/cancel写cancel_requested_at并NOTIFY mj_run_cancel；每步/每分片检查cancel_event，关闭供应商流，2秒内停止；部分文本以interrupted助手消息保存，run=cancelled，没有部分文本也明确状态。取消后不能再写事实/跟进或最终outbox；已完成合法工具保持回执，不伪装回滚。

飞书保留feishu:message:<message_id>幂等，每个有效原始message独立入库并保留时间/来源，2.5秒窗口内同一绑定用户的连续消息合成一个run。不能用拼接字符串替代多源quote映射；窗口边界、重复事件、重启、不同用户/channel都需测试。运行完成后走原outbox投最终文本，测试仅mock transport、不真发飞书。网页可从历史看飞书发起的回答与channel，不开发P4流式UI或P9卡片。

ConsultationService.submit按core_owners.settings.runtime（默认v3）固定本轮runtime；已排队任务不因owner开关变化偷换运行时。管理命令 `python -m mingjing_core.tools.set_runtime --owner <合成owner> --runtime v4|v3` 只用本机显式认证管理路径，不接前端owner任意修改。切回v3后新run仍走旧预算、旧runtime和core3.0。P1全局端口开关仍off，v4显式注入P1端口不自动开启v3 opt-in。

M5真实PG/MockTransport测X03/X04/X05/X07：同线程双消息严格串行，不同线程与两个lane可推进；取消延迟用真实单调时钟记录请求到HTTP流close及终态，不能用FrozenClock假装2秒达标；租约丢失旧worker拒写；NOTIFY与兜底都能claim。HTTP/DOM测试证明旧前端完整发问并显示回答；不改web/前端代码。v3→v4→v3各一轮比较实际runtime、信封和旧回归。

### M6：正式验证、报告与stage计划（后续阶段完成门）

P0评测框架增加真实PG的V4Target与--target v4选择，脚本ModelPort驱动真实Agent工具/应用服务；不能用FakeTarget直接写预期db。扩展参数/目标支持而不修改旧80 YAML、v1/rubric或今日c21报告。v4模型/配置/提示词/源码/判分契约都留摘要；同口径比较只用有资格比较的同场景/同断言/同judge/rubric，旧v3不适用项单列，不能冒充0分改善。若需要新的场景脚本动作格式，使用独立v4动作fixture/版本并明确比较限制。

正式P3脚本范围是T01–T14、M01–M04/M09–M11/M13、R01–R09、Q01–Q07、TA01–TA03、D01、S01、X03–X05、L01（47个ID）；每个必须走真实业务而非仅工具单测。X07另有网关集成，U4/U7另有PG扩展用例。L01使用P1四协议/能力fixture回放同一循环验证可移植性；没有对应Key不写成四供应商实测通过。

实测仅由root在用户在线且本聊天明确“开始”后按批安排，夜间零任何真实模型请求（含探针）；T/R/Q各类≥80%、S类100%（S01–S04），没有真实报告就明确未验证。主/评审均k3-256k，等价性≤20次先完成且单独授权；与P0 k3不同模型标识不可相减。每批≤10，滚动5h≤80（目标/judge/probe/全部HTTP重试），批间20分钟；任何续跑都需要用户新的批次开始授权。quota5h只记恢复时间、weekly置顶线上影响、monthly/Access terminated/concurrency立即持久全停。不得各建账本或趁E1等待自行请求。

M6叠加v4.2：新增`date_calc`只读工具（diff/add/age/weekday/农公历互转），复用P2 timekit/lunar-python，≥30例跨年闰月/月末/年龄/inclusive；description逐字采用增补A首句。ask_user必填slot并含changes_conclusion；clarify_slots存在thread.data，unfilled/filled/declined/conflict由程序转移，7天过期、≤5展示、同槽第3次返回slot_exhausted且继续回答；拒答正反各≥15，CL01–05集成。crisis.yaml逐字fallback_text与号码一致，危机规则命中后模型content/quota/concurrency/unavailable或20秒无正文时直接模板交付、不调评审，下一轮再尝试；D4不登记或自动联系紧急联系人。号码模板仅按设计接线，若实际需要向用户提供热线时由对应官方热线工具核验。完整助手消息同epoch原样含reasoning/signature/tool_calls回传，新用户轮关闭旧reasoning；tool_choice只auto/required，要纯文本就不传tools，指定函数/none禁止。system v1.1.0逐字增加增补H全部文字，告别规则正反各≥15并ctx.farewell进run meta，P6再实现正式结构审查。

19号DC01–04/TR01–03/CL01–05/K04–06脚本target v4必须全部通过，FW01暂作评审要点；P1b合并后加K01–03。19与P5b SP候选归契约v2.3，父v2.2；冻结v2.1、v2.2计分数据不改，不把新场景成绩与旧分数直接相减。DC/TR/CL真实合计≥80%只纳入获明确授权的正式P3批次，不另加无人值守批次。缓存命中率仅记录，缺供应商字段记null。

### M7：最后接入P1b U38与体积恢复（依赖P1b合并）

P1b实际合并前只按现有ModelPort完成离线脚本，不写假guard。合并后AgentDispatcher每次调用guard.acquire(role,lane)，interactive/background明确，子Agent继承lane；评测/probe仍root与授权闸门。后台拒绝回队列并保留deadline，交互在全停标志下回友好说明，危机走非模型模板。每次真实HTTP attempt（含重试）由唯一入口记账与获取槽位，端口总调用数不得替代actualPOST。

每次模型调用前运行M3a输入守卫及P1b最终序列化1.8MB体积守卫；单个工具结果>8k token时只把有效summary+alias注入，全文在受控journal。捕获payload_too_large/token_limit只允许将最早可压缩工具结果替换后重试一次并再次计量/计费/授权检查，不删除同epoch完整助手reasoning或伪造tool_call配对；无安全可压缩项或第二次失败就交付最后文本/友好兜底。K01–03/K06用真实PG+MockTransport证明预算/并发/重启停止标志/字节量/压缩计数与网络0/1/2次；全部0真实API。账本actual输入与预估/上界分字段，取值未知null。

产出 `docs/v4/release/P3_stage_plan.md`，包含精确待部署提交、迁移/配置、owner单独切v4、健康/对话/取消检查、回切v3、保留v3依赖与数据回滚、E1开关边界。该文档是计划，执行stage需用户对那次操作明确授权，本轮不执行；不把计划存在当stage验收。按AGENTS§11写阶段回执，CI绿且全部正式标准有证据才可称P3完成；当前保持draft，不合并。

## Concrete Steps（具体命令与预期）

下列命令为实际分支建好后的执行清单，当前草案阶段未执行。工作目录必须是root确认的P3 worktree，不能是E1冻结快照。Core解释器用该worktree环境或明确配置的Core Python；DSN/CHART_PYTHON从本机进程环境读取，不在命令/证据写密钥。

    git status --short
    git branch --show-current
    git rev-parse HEAD

预期分支为v4/p3-agent-runtime，基底可追溯到root填写的P1/P2合并，工作区无无关修改。新里程碑写第一条失败测试前先标Progress“已开始”，通过后记录命令/实际输出，不预填成功数量。

    python -m pytest tests/v4/agent/test_journal_pg.py tests/v4/agent/test_loop_pg.py -q
    python -m pytest tests/v4/agent/test_tools_pg.py tests/v4/agent/test_relative_dates_integration.py tests/v4/agent/test_tarot_guard_pg.py -q
    python -m pytest tests/v4/agent/test_context_pg.py tests/v4/agent/test_threads_pg.py -q
    python -m pytest tests/v4/agent/test_commit_gate_pg.py tests/v4/agent/test_envelope_compat.py -q
    python -m pytest tests/v4/agent/test_dispatcher_pg.py tests/v4/agent/test_cancel_stream.py tests/v4/agent/test_feishu_queue_pg.py tests/v4/agent/test_runtime_switch.py -q

这些是拟新增测试文件，尚未存在；必须随对应实现落地，测试中PG不允许替身。每个里程碑也运行已接范围的脚本target，只有--target v4正式接通后执行以下接口，禁止把当前不支持的命令输出记成成绩：

    python tools/eval/runner.py --mode scripted --target v4 --scenario <该里程碑已接通ID> --output docs/v4/evidence/P3/scripted

阶段收尾再跑：

    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted
    python tools/eval/runner.py --mode scripted --target v4 --scenario T01,T02,T03,T04,T05,T06,T07,T08,T09,T10,T11,T12,T13,T14,M01,M02,M03,M04,M09,M10,M11,M13,R01,R02,R03,R04,R05,R06,R07,R08,R09,Q01,Q02,Q03,Q04,Q05,Q06,Q07,TA01,TA02,TA03,D01,S01,X03,X04,X05,L01 --output docs/v4/evidence/P3/scripted
    python -m ruff check <新增及修改的Python文件> --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check --line-length 120 <新增及修改的Python文件>
    git diff --check

现有Core测试计数随合并基底实测填写，不永久写死553以免把增加测试当错误；须保留旧553行为覆盖。旧前端DOM/截图命令按当前已有浏览器测试入口补充，实际使用本机服务和合成owner，禁止外部stage URL。新代码AST审查单文件≤400行（硬600）、函数≤60行、行≤120列、类型齐全；不整体重排旧大文件。真实live命令只由root在共享预算接线审查通过后记录，不在草案放可误执行的独立probe命令。

## Validation and Acceptance（正式验收映射）

| P3标准/设计要求 | 输入与可观察输出 | 必须保留的证据 |
| --- | --- | --- |
| 1 脚本与实测 | 上述47脚本ID全通过；主模型T/R/Q≥80%、S=100%；事实硬错不能被judge高分盖过 | PG业务回读、目标/评分身份、分类报告、与有效基线比较限制、真实POST账本；未跑明确空缺。 |
| 2 崩溃恢复/取消 | X03每种写工具跨崩溃窗口后恰一事实/跟进/draw/outbox；X04停止后≤2秒流close，partial=interrupted | 多连接PG记录、step/operation统计、安全异常类、实测单调时钟延迟；不含正文日志。 |
| 3 并发/通道 | 同线程两run时间区间不重叠；不同线程/lane同时前进，全局≤配置并发 | 实际PG竞争、租约/NOTIFY与轮询、开始结束安全事件；进程重启后仍成立。 |
| 4 旧前端 | runtime=v4下一条消息经过队列/Agent/提交，旧DOM显示完整回答；历史core3仍显示 | DOM断言或手工截图、实际API、合成owner；只HTTP200不够。 |
| 5 飞书入队 | X07 2秒内3条合成事件保留3个原消息但1个run；完成后mock outbox只一次 | MockTransport请求与PG行数/来源；不真实发送。 |
| 6 路由回滚 | 同owner v3→v4→v3三轮固定各自runtime，旧v3限制/行为不变 | 管理命令结果、run/runtime/envelope及旧回归；全局端口仍off。 |
| 7 stage计划 | 计划包含切主owner v4与回滚、迁移和健康检查 | P3_stage_plan.md；“未执行，需具体授权”。 |
| 8 ExecPlan/回执 | Progress等四节与实际实现/证据一致，未完成项逐条列出 | 正式ExecPlan、AGENTS§11回执、PR draft/CI状态；本轮不要求整阶段完成。 |
| U4 | 从原用户消息写起，TM01/02两轮日期稳定；正反例各≥20 | PG fact/followup的event_at/said_at/source_refs与确认分支；不预置归一结果绕过写入。 |
| U7 | AX02先零新draw护栏，再新用户明确坚持生成唯一新draw，旧牌不变 | PG draw/readings before/after、同问题/相似度版本/边界/身份校验。 |
| 工具/危机/上下文 | 参数、≤15可见、ask_user新轮、S01规则正反各≥15、引用与预算、M13无痕隔离 | 真实Toolkit/ModelPort消息、PG线程/检索/撤销、提示词逐字与版本hash。 |
| D2上下文硬门 | R07 300轮/PG 10,000条、>120k压缩、180k内发送/required溢出0 POST、三次60k提醒 | 最终请求meter来源/模型/version、逐轮预算trace、原文哈希不变、约束来源仍在、实际usage与估算分开；缺可信Kimi上界写未验证。 |
| v4.2 A/B/C | DC01–04/TR01–03、date_calc≥30例、模块线parse_time_range≥20表达式对接 | 真实tool轨迹/FTS时间语义/JSON行格式、脚本结果；真实分批授权后DC/TR/CL合计≥80%，未授权0。 |
| v4.2 D/H | CL01–05、slot第3次拒问、拒答/告别正反≥15、FW01无问句 | PG线程槽状态/原用户消息锚点、system v1.1.0逐字差异与hash、farewell meta；P6结构审查尚未接写明。 |
| v4.2 E/F/I | K01–06、同epoch reasoning原样/跨轮不回传、tool_choice无named/none、危机20秒兜底 | MockTransport请求体断言、PG持久守卫/计数、实际单调时钟延迟、全停时无HTTP；真实probe待明确开始。 |
| v4.2 G | L5块内旧前缀不改写、40轮后10轮前移、固定工具顺序 | 字节diff及源revision、缓存usage存在则统计；整块L5一致矛盾待大脑，缺实际cache字段不写命中。 |
| F1/P5b B（后续） | M3完成后space/topic/route API幂等revision、case兼容、SP01–04/SP06后端 | 真实PG应用→撤销逐字段、owner隔离、topic/跨区摘要撤销闭包、route_changed协议小版本；A/C和stage旧史整理不归本任务。 |

## Idempotence and Recovery（幂等、迁移、回滚与隐私）

复用P2现有迁移校验，禁止编辑0001–0007；0008归P1b、0009/0010/0011归P5/P11既定迁移，不得抢号；确需新索引/线程持久锁结构时由root先与P1b/P5统一编号后前向迁移，由迁移角色在合成库验证两次运行无额外效果、运行角色无DDL。正式部署前另行备份/授权，本轮不触碰真实数据。回滚以owner runtime=v3与停dispatcher的受控路径为主，不删v4表或正文来“还原”；保留新数据供恢复/隐私处理，旧版本能否读取新schema须在stage计划注明。

Journal恢复需有效当前lease，旧worker即使仍有内存结果也不能提交；崩溃重claim不重置操作指纹或自动换epoch逃过幂等。epoch用于规定的一次撤销再生成，不用于无限供应商重试。未完成模型步骤重发可能产生新的回答，实际调用必须记账；已经完成并持久的模型步骤不再请求。不可恢复或配额停止留状态和安全error_code，不吞异常或伪造完成。

撤销从用户原话区间/事实传到note、proposal、followup/reminder、助手消息、steps/events、claims、缓存引用。复用P2 privacy_foundation清空受影响run的step.output/event.payload，新增注入/引用血缘必须能被闭包找到；删除后恢复不可把旧journal正文重新注入。对未来P5摘要/画像只声明接口，不造后台任务。事件正文提交后24小时清理，step正文30天后留元数据，用本机可测清理函数/命令与Clock验证，不改生产cron。无痕正文不可流入反思或主线程检索。

工具只在本机PG写行，不发网络；排盘仍是既有隔离子进程，模型只经P1端口。日志/ExecPlan/PR只保留合成ID、错误类型、计数、摘要，不保留用户正文、reasoning、DSN或key；LANGSMITH_TRACING/LANGCHAIN_TRACING_V2保持false。退出测试只清理由当前测试创建且验证名字/owner的schema，不清理E1或别的工作树。

## Artifacts and Notes（产物、证据和待决项）

正式仓库产物为 `docs/v4/execplans/P3_agent_runtime.md`、`docs/v4/evidence/P3/`、`docs/v4/release/P3_stage_plan.md`，以及阶段回执。证据目录按M1–M6分组保存测试命令/输出、运行身份/提示词hash、PG安全统计、脚本JSON/MD、取消延迟与DOM截图；原模型全文仅限明确合成评测证据，不放操作日志。真实调用只引用共享账本的安全计数和状态。

历史草案保留在 `task/work/daytime/P3_agent_runtime.draft.md`，M3a设计草案见同目录`P3_context_guard.slice.md`。正式计划现已落在本分支；M3a离线首切片的9个代码/测试文件、63项目标测试、678项全v4回归及真实PG300轮/万条消息证据已提交，见本节正式证据目录和Progress。新增schema为0；实际token计量与完整P3里程碑仍未完成，不将历史草案或预期当作验收结果。

需要大脑确认但不阻止M1的事项：无痕线程中用户显式要求持久提醒时如何与“不写记忆”兼容；首版高相似塔罗问题规则若边界测试暴露误伤，列具体样例再裁定；consult_specialist选择P3末尾或P8须在正式进度明确。默认先执行不依赖这些决定的M1/U4：无痕不生成长期实体、塔罗完全相同问题护栏先闭环，复杂相似度不冒充完成。

需要用户/外部资源的事项：stage那次执行授权、每一批真实E1/E2/P3与probe的开始指令、k3-256k等价性≤20次的实测；无授权就保持0真实，不设定时自动恢复。需要大脑的事项另含L5整块逐字节矛盾与可信token计量器/协议framing上界，先完成不依赖这些的脚本和PG装配。用户不在线时统一写入每日汇总“需要用户/需要大脑”，立即切换到可进行的里程碑，不等待、不自己改产品设计。若主模型L01频繁协议/格式错误，先保存具体失败与重放证据，再由root提出模型选择，不能偷偷换被测模型。

## Interfaces and Dependencies（拟定接口与依赖）

公共接口沿用RuntimePort.execute；`AgentLoopRuntime`接收repo、ContextEngine、ModelPort、Toolkit、Journal、Clock、RuntimeConfig和emit/cancel_event。Loop不依赖供应商字段，规范化ChatMessage同epoch完整回传reasoning/signature，跨用户轮清除旧reasoning；P1b端口能力只做供应商协议映射。Journal键为owner/run_id/epoch/seq，输入指纹绑定工具名/规范参数和有效来源；ToolContext包含受信owner/subject/thread/run/source/lease/operation_id，模型不可覆盖。

`ContextEngine.build(run)`返回messages、alias_map、injected_fact_ids/source_refs与安全预算统计；TokenMeter.count(request)->MeterResult包含model/meter_version/estimated/upper_bound/可信标志，最终序列化调用方再次校验；Toolkit执行结果返回数据/回执/ends_turn/安全summary。U4解析结果明确resolved或needs_confirmation，不以空dict代表失败；U7结果明确recent_draw_exists或新draw，并保留已有TarotService错误类型。新工具参数用Pydantic v2，schema_flatten走合并后P1实现，不新增远程服务依赖或Python包升级。

拟新增HTTP字段：POST /api/chat的thread_id/incognito，旧session_id仍接收并映射topic_id；POST /api/runs/{id}/cancel；现有GET chat/runs/history读取core3/core4。路由owner仍来自auth，thread_id必须校验归属；UI参数不改变subject授权。后台lane/parent_run_id保留未来P5/P7接口，本阶段不启动反思或发送器。NOTIFY payload只放受控ID，不含消息正文。

## 修订记录

- 2026-10-18 22:04 +08:00：纳入夜间新顺序、最新B1裁定、持续续作/小时日报/08:00汇总与零服务器/零真实调用边界；明确先补尚未存在的loop依赖，保护模块/前端/命理独占范围。

- 2026-10-18 16:22 +08:00：创建task草案，依据最新P3/U4/U7、15号开工范围及P1/P2只读代码，基底与各实施里程碑完成状态明确留待root合并后填写。

- 2026-10-18 本轮：纳入18索引§4a最新D1/D2/D4/D5、P3 v4.2 A–I、主线/模块/前端边界；加入M3a token守卫首切片、真实PG300轮/万条验收与P5b B后续里程碑，保留未决计量/缓存矛盾，不发真实请求。

- 2026-10-18 本轮：仅补充F1的路由授权/本轮修订、batch撤销不复活来源、跨区/无痕/敏感边界及SP07服务端脱敏责任；其余实施范围与A/C分工不变。

- 2026-10-18 17:34 +08:00：P2精确头CI全绿合并后创建正式分支，M0落盘；F1含P5b B全范围、完整M3依赖及A/C责任边界，未启动F1。

- 2026-10-18 18:02 +08:00：记录63项目标/PG长线程与离线限制，修复源时点/撤销/回执/mixed-epoch边界；F1仍未开工，补B1仅计划状态。

- 2026-10-18 本轮：维护四个活文档段落，记录Journal39项子范围及未接线边界、用户授权A只读盘点和B1具体操作单、23号B1模型决定与Charts锁例外；不把M1/P3或stage标完成。
