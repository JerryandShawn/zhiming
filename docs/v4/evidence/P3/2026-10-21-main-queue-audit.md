# 主线队列库存审计（只读）

快照：2026-10-21 10:49–10:53 +08:00，北京时间。依据本轮完整读到的交付指令板v2、33号第一节/无尽储备、28号、29号〇-A、本机主计划/日报/切片证据与git worktree快照。本轮只新增本文，未改生产/测试/他线文件，未运行pytest、PG、Linux/服务器探测、模型或飞书，也未发跨聊天消息。下列“已有”指对应范围有证据，不能读成阶段验收或部署通过；各分数不相加。

## 先决裁定与版本归属

指令板仍v2：30号明确No-Go，先补B1；遇到环境依赖就返回28→29〇-A→33队列，不能空等。两次非破坏环境尝试已耗尽，禁止第三次修复/重试Docker或WSL，不建立SSH。B1固定b9，0005–0007；0008另轨，0009预留P5b B。新增代码不改变固定b9，不因Windows组件绿解除stage五门。

本机只读Git归属（不是本轮远端/CI实时查询）：

| 工作树/分支 | 本机head | 此快照能说明什么 |
| --- | --- | --- |
| 主树 v4/p3-agent-runtime | 1fe5149cbe9de10632f97f84003ac833a4a4f65f | 含最新B1元数据/正式启动与第三方执行后来源片；后者只有33新/40旧窄证据，不能继承10点宽验 |
| v4/integration | 6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68 | 已合P1b，之后文档续作；未合P3/P4/P6/模块/P8/前端 |
| P1b/P3 wire | c0892a40a8a91630f82a8a61bb7c989c02e2129c | 组合候选及固定ff4宽验回执，不是已进入integration |
| P4 wire | a1270174e6f64cfe1abe915a09836647c1da3484 | 独立、默认关闭的流式候选；活跃代理继续，勿重复接线 |
| P6 wire | 6184b318e59bb52c2290b4c23bd2312a012b3206 | 只读校验桥默认关闭；关联PR11的成功CI实际是merge preview，不是head自身树 |

完整结果各自钉源：主树4f042e7→6f8c44aa/tree58c5381e为2299通过/1严格xfail/1warning、Core582；wire ff4的Core583；P4 95df的v4 2751通过/1严格xfail/1warning。新P4 timer/cursor/joint及最新B1片不在这些固定源，不能回签。见本树`2026-10-21-1000-pinned-regression.md`、wire/P4各自回执；本轮未联网重核新CI。

## 28主队列与储备：哪些无需重做

| 项 | 已有范围 | 真正剩余/阻塞 |
| --- | --- | --- |
| 0 上夜收尾 | cc372c7等价远端及三日报已有推送/CI历史回执 | 不再重做；历史03–06中断不补造 |
| 1 冻结事件/core4 | 文档、Schema、类型/序列化与89项独立契约证据 | 后续新字段按兼容门，不能据此算P4持久订阅完成 |
| 2 Z1–Z5 | 估算/epoch/工具可见性/无痕确认/迁移裁定均有切片；常驻/条件15上限不再改第二套 | 真实K3 tokenizer未配置，新增依赖未获例外；合成meter不能放行真实调用 |
| 3 M4 | v3 ChartsService共用适配、工具注册、memory_update/profile请求、date_calc服务端接口、U7均有PG证据 | P8原生替换属33§7；U4按Z6仅接口/替身，接模块实现属P5；date_calc公开披露待大脑 |
| 4 M6 | RuntimePort、安全提交/core4、core3读取端、一次修订、正式提示词/U41和严格own-effect恢复有独立证据 | 真实模型质量、全局组合与历史前端回执未验；不重做已经修复的case效果链 |
| 5 M5 | life/private、自然无痕、run写屏障、inbox证明/fallback、Feishu2500ms持久合并、线程HTTP候选已交 | QueuePort逐条撤回、asked确认、附件等新API差额在P10，不把现取消整个run当替代 |
| 6 M7 | 双通道、线程串行、LISTEN/NOTIFY、续租、实际回环HTTP两秒取消有组件/端到端证据 | 新P4跨进程事件通知与清理另轨；不是线上延迟或真实供应商验收 |
| 7 M8 | --target v4真实PG/ScriptedProvider；原47最近完整报告46/47、独立扩展13/13 | X03四条网页写入/飞书Outbox混绑断言待大脑，不能造Outbox/改评分报100%；M8/P3不能整阶段完成 |
| 8 P1b | 中央HTTP守卫、可信scope/角色、人工CLI、≤20次等价性替身及P3 worker接线有独立wire证据 | 尚未进入integration；真实等价调用/人工E1仍0，必须用户在线明确开始，不因周授权自动开始 |
| 9 B1 | 增量入口、B7新CLI、B3 producer/consumer、Windows真PG、App分阶段、B6十三资产、权限/来源加固均已交 | Linux同一B2→B3→回填→B7→fence全链未跑；下述两项b9真实阻塞不是环境恢复即可消失 |
| 10 路线图 | merge_roadmap已有顺序/迁移/测试闸门 | 其08:14状态段已落后，只能作流程；执行前须核当前head/实际CI checkout |
| 储备a/b/c | 连续自写/撤销再生成/core4读取、P6默认off草稿、塔罗c/r全血缘、case生命周期索引、181k分词性能均有后续证据 | 不按早期unchecked重做。P6整阶段/专业复核仍未接，分词优化也不等于K3 token计量 |
| 储备d | 已补多组故障/恢复/owner/epoch/撤销反例与文档 | 本线新增代码覆盖≥90%、全Runtime p95与所有警告清零没有完整验收证据 |

定位入口：`P3_agent_runtime.md`、`P3_M8_scripted_v4_2026-10-21.md`、`P3_M4_tools_2026-10-21.md`、`P3_m5_ingress_inbox.md`、`P3_m5_natural_privacy.md`、`P3_m7_dispatcher.md`、`P3_M6_readers_2026-10-21.md`及对应evidence。主总Plan顶部/Outcomes仍主要到09:41；其历史行“tarot/case done-archived/config/并行未完”等已被后续独立计划/证据推进，不能机械按checkbox重开旧工作。

## 33第一节的当前映射

| 33主线项 | 当前分类 | 下一真实交付门 |
| --- | --- | --- |
| 1 P3收尾 | 实现候选已有，未验收 | 原脚本100%、X03裁定、旧DOM/真实encoder分开列缺口；阶段回执必须诚实未完 |
| 2 integration | 仅第一步P1b进入，后续未合 | 复用已存在wire，逐个精确普通merge与组合Core/v4/Charts/web回执；不重建、不rebase、不强推、不合main |
| 3 P4 | 独立候选实施中 | M1事件事务通知、M2合并/timer、M3监听、严格cursor已有；M4新JSON/旧协议/塔罗、M5清理墓碑、完整M6及间歇诊断未完成 |
| 4 P5+P5b B | 主线未见实体/API接线 | 主树迁移仅1–7；area/topic目前仅run元数据，无topic_route或区/话题API。须接模块/U4、0009、授权上下文与M/R/F/KU/TM/MS |
| 5 P6 | 默认off结构/lint桥独立草稿 | v2独立critic/校准/专业claim revalidator/farewell及P8一致性接线未完成；record_only不变 |
| 6 P7 | 单工具/本地提醒不等于完整主动性 | 模块调度/晨报→PG领取/Outbox、K1/K2、D4默认关、P/AX全脚本 |
| 7 P8接线 | v3适配器保留，原生未替换 | P8 chart_compute/skill、四工具、synastry consent、boundary_alerts、C类及E2脚本 |
| 8 P9 | 仅M5合并入队基础 | action token PG单次能力、官方卡片/CardKit/action回调、假飞书完整链；不得真发送 |
| 9 P10后端API | 已有线程/run/events索引，非全night端口 | 画像/记忆提案/设备/报告/整理/今日页/区话题/inbox逐个真实契约；asked/插话撤回/附件明确未齐 |
| 10 P11 | P3切换管理与计划局部 | B2–B6开关、v3退役开关、各stage/prod runbook及本机演练未齐；本树release未见B2–B6执行单 |
| 11 全脚本 | P3子集与独立扩展，不是全题 | 80+附录B+19号52题v4候选报告；B2三十题≤10/批真实计划，实际调用等待人工开始 |
| 12 储备/无尽储备 | 多项可离线继续，未系统交付 | 全新API安全审查、Runtime p95、索引、日志/指标、v4新表备份；新增代码90%覆盖等仍需独立基线 |

P4当前并非全未做：10:45游标片98项目标有独立证据；10:50联合双开关/跨进程HTTP最新3/3，但前两次跨进程超时缺安全诊断、根因未实证，不能称稳定。该片由活跃代理交root，不再另开第二套监听/timer。P6成功CI按10:31更正，只用于实际merge preview c79b9e6a/tree1e813551；19个skip是B1 App PG8+restore PG11未设显式管理DSN，不能说全体无skip通过。

## 阻塞与允许继续的边界

1. **B1环境**：两次额度已用尽，等用户回家处理Docker/WSL；本轮不再修。**B1候选数据**：schema4真实撤销引用未迁的core_embeddings等表，源保持4时不能生成latest；非空deleted_draws重放后目标再次导出丢失tarot-delete收据，verify_monotone报STALE_WITHDRAWALS。原成功要求首红和“故障被安全拒绝”绿探针分开；不得改b9/假insert收据/删字段放过。delta克隆仍仅设计，不能解除后者。
2. **P3验收产品差额**：X03原网页/飞书发送边界、date_calc披露由大脑裁定；实际K3 encoder受不新增依赖约束；真实模型E1/E2必须用户在线明确开始。可以继续脚本/契约，不能后台试探。
3. **他线责任**：旧DOM receipts显示属于前端；P8/skills/knowledge与模块纯源按所有权只读，不去他树修。前端端口对接前必须冻结主线真实API，不能把模拟数据当已持久。
4. **源与证据**：主Plan/路线图/子Plan历史Outcomes落后不是新业务缺口。更新应新增“当前判定+证据”，保留原失败，不能把固定10点宽验移到最新源；11点窗口由root统一安排，本审计占测试槽0。

## 后续三个可离线实做选项（由root分配明确文件后实施）

### A．优先：把已验证wire带进正式integration并冻结组合门

复用已有P1b/P3 wire的scope、私有codec、socket/取消与fixture修复；先比integration实际P1b头、最新主P3和wire三图/源码树，再普通merge指定精确源，不重新实现守卫。先核0001–0007不变、0008归P1b及额外Schema/loader来源；冲突保留两侧保护。按33每步写integration回执并在00–15窗口跑组合Core/v4/Charts/web，PR继续Draft。原X03/旧DOM/encoder与B1独立No-Go照列，不以integration成为可上线或P3已验收。此项是主队列2真实未做的归档/组合交付，避免继续只在多个wire重复窄验。

### B．P5b B第一小片：0009区/话题实体和可信路由上下文

在root选定的integration子分支，先读22/P5b B与模块U4/记忆契约，限定主线B部分；复用现ContextEngine，不重做它或模块A/前端C。首片做0009增量/重复verify、owner/subject/revision实体服务、topic_route受信选择和api_*.md；迁移不能进B1包，真实旧对话整理仍只dry-run。隔离PG覆盖跨owner/topic、无痕禁长期化、稳定operation_id/CAS、撤销来源、不因分区扩权；API/上下文可分片，不一次承诺全P5。当前主树只有area/topic字段投影，故不是重做已有API。

### C．无外部依赖的完整Runtime p95基线与热点证据

新增独立工具/证据，不碰活跃P4或前端文件：用真实本机隔离PG+ScriptedProvider，固定种子/TZ/预热/样本，测完整run的context→model脚本→只读/写工具→commit的p50/p95/查询量，另列恢复/同线程排队；所有模型HTTP/消息均0。复用已有tools/benchmark_p2.py的本机DSN/专用schema安全门，但不重复其1万消息snapshot或181k分词成绩。先出实际基线再只优化可测热点，不把脚本时间当供应商在线延迟或靠放松断言取收益。该项直接对应33§12，现有库存未找到完整Agent循环p95工具/报告，源可独占新增文件，适合其他代码等待组合时推进。

三个选项都不要求用户夜里回复、加依赖、服务器或真实模型；真正的产品/候选修复裁定写待决，不阻塞其它离线实施。不是现在就授权本审计代理修改这些源码，本轮产物只有本文。
