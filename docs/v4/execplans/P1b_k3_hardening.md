# P1b：加固 Kimi Code 错误、协议、额度与调用入口（开工）

本 ExecPlan 遵循 `.agent/PLANS.md`，四个活文档段落随实际证据更新。正式分支`v4/p1b-k3-hardening`于2026-10-18 17:34 +08:00从P1/P2均已合并的`v4/main@b9a89b6f84f7bebb640de080548010859aae630c`创建。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b`。尚未实施，真实请求0。

## Purpose / Big Picture

让会员调用具备一致的错误动作、可追踪的真实 POST 计数、跨进程在途限制，以及完整工具循环推理回传。模型、评审、后台、评测和探针共享入口；错误或风控不能靠换同一会员的模型绕过。默认 v3 路由与旧业务预算保留。真实请求只在用户在本聊天明确启动相应批次或探针后执行。

额度账本是只记录时间、模型、状态与用量的持久表；在途槽位是一次HTTP请求期间占有的跨进程许可；工具循环是模型请求工具、收到结果后继续回答的同一运行。它们不改变来源授权、固定塔罗、owner隔离或送达不明不重发契约。

## Context and Orientation

设计来源：原 P1 提示词、17 号研究 §6、`docs/v4/prompts/supplements/P1b_增补_K3会员端点加固.md` 与同目录 `00_索引.md` §4a。正式基底及P2合并号为`b9a89b6f84f7bebb640de080548010859aae630c`；P2候选1444a49的CI 39114527541所有步骤成功后才合并。P1 已于 2026-10-18 合入 `v4/main@7b45a781921e6fa2e875319a12af433f0cf505b4`；P2已合并，原P1、P2阶段分支保留。

复用 `models/port.py` 的规范消息与 tool_cycle、`models/transport.py` 的 HTTP/SSE、`models/provider_diagnostics.py` 的受限公开诊断、`models/metering.py` 的物理 POST 前计数，以及 Registry 的角色解析。P2 已有迁移校验/权限授权；迁移 0008 为本阶段预留。

文件归属：主线修改已有 models/config/runner/probe 与迁移和接线；独立模块线拥有新增 `models/quota_guard.py` 核心及其单测，主线消费真实实现、审查接口、做集成，不另写假守卫抢占。P3 的上下文压缩、危机兜底、工具循环与上下文 token 守卫属于 P3；不改 web/**、P10、P8、charts/skills/knowledge。

## Progress

- [x] (2026-10-18 16:50 +08:00) 阅读 P1b、P3 增补及索引 §4a；先建立 task 草案，真实请求为 0。
- [x] (2026-10-18 17:34 +08:00) M0：P2精确头CI绿并合并，建立`v4/p1b-k3-hardening`与独立工作树，正式落盘本计划。
- [ ] M1：U37 错误分类与 HTTP/SSE 动作表、公开诊断回归。
- [ ] M2：U39 推理/签名、禁关思考、角色 effort、采样与工具选择/体积守卫。
- [ ] M3：0008、真实 PG 用量/停止状态、消费模块线 quota_guard、所有调用入口接线。
- [ ] M4：人工分批评测与探针启动门、报告身份与 k3-256k 候选配置。
- [ ] M5：用户明确开始后运行获授权的探针/等价子集，再决定是否具备实际切换证据。
- [ ] M6：完整回归、覆盖率不低于 P1、CI、AGENTS §11 回执，保持草稿不自行合并。

## Surprises & Discoveries

P1 的实际物理 POST 计数由 ContextVar hook 提供，旧 ConfiguredModel 仍是 E1/v3 默认路径。仅给 Registry 加守卫不能据此声称所有会员入口已覆盖；必须列出旧适配器、重试、评审、探针和 runner 路径并实际验证。若最窄接线超出增补列出的文件范围，先写清设计冲突与候选改法，不暗中放开范围。

旧 E1 已准备的 k3 冻结清单是历史准备物；未运行、没有成绩。新 D2 及唯一守卫生效后需重新准备可验证执行身份，不把旧清单改名为 k3-256k 实测，更不把不同模型分数直接相减。原无人值守 coordinator 已禁用。

## Decision Log

2026-10-18 / 用户明确决定与索引 §4a：D1 继续全部使用 Kimi Code 会员端点；总在途≤2。`concurrency_limited` 或 `Access terminated` 立即全局停止并置顶通知，优先于增补默认的仅降至1/暂停后台24小时。停止必须持久化，不自动换 key/同会员模型或定时探针恢复。

2026-10-18 / 用户决定：E1/E2 只在用户在线且本聊天明确“开始 E1/E2 第 N 批”后执行，每批≤10；夜间不发任何真实模型请求（含探针）。探针同样等用户“开始”。旧15号的自动续跑不能替代逐批授权。窗口仍≤80真实POST/5小时，目标、评审、探针、内部重试共同计数；20分钟间隔仍执行。没有授权只做离线 MockTransport 和真实隔离PG检查。

2026-10-18 / D2：主模型与评审目标均为 k3-256k，保留独立上下文。切换前要求≤20次等价子集；当前未获探针启动授权，因此只准备配置/验证门，不能宣布已实测等价或已在网站切换。新模型/effort/协议作为独立报告身份，P0 k3 成绩不直接相减。

2026-10-18 / D2上下文附加要求写入P3：目标约30k token，>120k压缩旧层，输入硬上限180k，单工具>8k摘要；每次写用量账本，连续3次>60k在汇总提醒。P1b提供输入/缓存/输出用量与错误，P3负责装配/压缩与不丢关键约束；缺供应商用量记null，不伪造精确token数。

2026-10-18 / D3-D5：准确时辰优先time_basis核对，事件反推低优先且不外部名人评测；使用时长提醒默认关闭，不登记紧急联系人；E2只跑2025子集。P1b不越界实现P7/P8，只在报告与调度入口保留这些边界。

2026-10-18 / 迁移：0008_model_usage由P1b独占，P5对应0009/0010，退役LangGraph0011。只新增顺序迁移，不修改0001–0007；若已知链机制出现真实冲突，记待决并切换其他里程碑。

## Outcomes & Retrospective

当前正式分支与ExecPlan已建立，旧E1自动入口保持禁用；没有P1b代码、迁移或探针结果。P1/P2均已CI绿并合并。正式开工后更新实际范围，离线证据与真实探针分开；未完成真实探针时整阶段不能报完成。

## Plan of Work

M1以官方原文或历史受限公开诊断为错误夹具依据。403保留严格permission_error+usage limit规则并扩展monthly/concurrency/access terminated；402一次60秒重试、429按rate/overload退避、400区分reasoning/size/token/content，流式同分类。诊断只留允许字段与审核过的公开提示，不能把任意响应前240字带出边界。所有终止型错误不重试/不换同会员模型。

M2先查官方 Kimi/Anthropic effort 字段；不能凭猜测新增参数，缺文档且无授权探针时采用服务端默认high并明确fast未验证low。会员k3*禁关思考；固定采样不发temperature/top_p。工具循环回传原始完整规范助手消息及推理/签名，新真实用户轮关闭旧循环；缺签名只计数，真实效果等待授权探针。禁止named/none且0请求，纯文字不带tools，单工具强制required。请求序列化>1.8MB预发拒绝。

M3用量表每个物理POST一次（含失败与重试），无正文；PG专用连接持有会话advisory槽，交互预留一槽，其他通道一槽，总在途≤2，不能持owner业务事务跨网络。预算份额/借用用真实并发PG验证；monthly、风控、Access terminated全局持久停，人工解除是显式操作。部署授权同步新表。接口guard.acquire/status/critic_allowed/background_allowed，与模块线真实代码核对后接线，不编造通过。

M4评测执行单批即返回，不通过--follow或定时器继续下一批；用户授权批号、场景上限、已完成场景、执行身份和共享账本绑定，重启不自动开新批。替身测试证明无启动授权0POST、批≤10、批间隔及80窗口保护。旧报告/基线不可覆盖。新增background角色仍用会员；主/评审256k候选有明确验证门，环境model覆盖不得静默退回k3或关思考。

M5用户明确启动后，按每次具体授权执行探针，非自动串跑所有suite。E1-E4总上限40、等价子集≤20且合计真实窗口≤80，所有探针经过守卫。正文不入探针日志，只记工具完成/参数核验/签名/缓存/用量。没有结果写未验证；变差/缺签名失败记待大脑，不私换模型。

## Concrete Steps

正式分支建立后执行（当前未执行）：

    python -m pytest tests/v4/models -q
    python -m coverage run --source=mingjing_core.models -m pytest tests/v4/models tests/v4/test_eval_framework.py -q
    python -m coverage report --fail-under=95
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test
    python -m ruff check <新增和修改的现代文件> --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check --line-length 120 <新增和修改的现代文件>
    git diff --check

PG明确core_test_main/127.0.0.1:55480，测试每例独立schema；Core/Charts环境隔离，清空Kimi/Moonshot钥及追踪。以上测试不能触发真实HTTP。任何真实探针命令只在用户明确开始后记录具体批次，不在计划中放自动可运行循环。

## Validation and Acceptance

增补八项逐项保留：错误→类型→动作实测表；真实PG三调用最多两在途（风控后全停）；月额度跨进程持久全停与人工解除；禁关思考拒启动；E1–E4探针真实结论；所有runner物理调用在用量表且lane=eval；CI及模型覆盖率≥P1约95%；计划与§11回执。新增D1全停/人工批门、D2模型身份及上下文账本映射另有回归。未获得真实启动授权时第五项标未验证，不能宣布整阶段完成。

对应19号候选场景K01–K03、K05的端口/守卫部分；07原有L01、X03–X05保持旧协议、恢复、取消回归。真实场景新定义归v2.3候选，不修改已冻结v2.1八十场景或分数。

## Idempotence and Recovery

用量写入与请求预留有稳定attempt_id，崩溃不能释放预算重发绕计数；在途槽由PG连接死亡释放，停止标志持久保留。重试每次都单独记数，排队未POST不当作已完成请求。迁移仅合成库前向验证，旧版本拒不认识schema；回滚先停新入口/owner回v3，实际stage迁移与生产回滚另需具体授权，本轮不执行。

## Artifacts and Notes

正式文件：docs/v4/execplans/P1b_k3_hardening.md、evidence/P1b、model-probe-<date>-k3-hardening.md、§11回执。当前草案仅task/work/daytime/P1b_k3_hardening.draft.md。待用户：每次探针/评测开始；待大脑：真实发现的协议/范围冲突及探针变差。所有问题写汇总后继续独立离线工作，不等待。

## Interfaces and Dependencies

依赖P1/P2合并；与P3并行，P3的正式守卫接入里程碑要等P1b合并。quota_guard核心由模块线供给，主线负责真实PG集成、迁移、Registry/物理POST接线及人工执行门。模型用量与安全错误不包含任何用户原话、思考正文、请求/响应、key或完整DSN。

## 修订记录

- 2026-10-18 17:11 +08:00：建立并补全task草案，纳入18索引§4a与明确人工开始门；P1已合并、P2尚在完整回归，不抢先建正式分支。

## U37首切片接口与旧测试替换依据

统一纯分类器`classify_error(status, payload, membership=..., surface=...)`返回旧ModelUnavailable兼容异常，新增受控kind与不可变ErrorActions。只读取完整嵌套error外壳；HTTP与SSE共表，SSE没有状态不捏造429。ModelPermissionError采用旧ModelPermissionDenied同类别名。公开诊断只保留审计句，不把任意响应前240字导出；新错误的原始正文不留在异常/日志。

主线拆分所有权：分类代理只改errors.py/provider_diagnostics.py/error_classification.py及新矩阵测试；root改transport.py/registry.py及下游eval兼容。模块线独占quota_guard.py。重试只在一个层执行：Registry构造adapter max_retries=0；直用adapter按同一ErrorActions执行。402最多2尝试（60s一次）；429/5xx/网络最多4尝试（1/3/9加抖动），总deadline/取消/可见输出进一步收紧。global_stop优先，无自动同会员fallback；没有PG接线时不能声称跨进程全停已经实施。

Decision Log补充（2026-10-18/Codex）：旧test_membership_quota_never_retry的429和500正文quota、streamed membership rate-limit和unreadable429断言保护旧“一律额度停”行为。P1b §A明确替换为状态优先的rate/transient动作；只修改这些已被新设计替代的断言，保留真实403额度1POST、隐私、取消、总deadline、不在已可见输出后重播的保护。Registry旧503两尝试用例按同一明确退避预算更新，不保留嵌套两套重试。84个先行矩阵中的未官方证实文案标格式推定，不称录制响应。

中心账本拓扑（后续M3）：所有业务库/评测/探针明确共用同一ledger DSN/schema/account scope；PG advisory锁仅DB内有效，不能各业务DB建独立守卫。拟用独立本机无正文账本数据库，配置固定ledger identity，缺配置失败关闭。每个物理attempt先预留、结束后终结，不能一complete只算一次或多层重复acquire。具体数据库/迁移安装仍未实施；不把方案当验收。

- 2026-10-18 17:34 +08:00：P2合并后M0完成，补U37接口/动作与旧测试替换依据，中央账本仍等模块接口接线，真实请求0。
