# P3：为 Agent 运行时纳入 U4 日期写入与 U7 塔罗重复请求规则

本 ExecPlan 遵循 `.agent/PLANS.md`，四个活文档段落随 P3 实际实施更新。本次提交负责研究增补的接入计划与 v2.2 场景定义，不代表 Agent 运行时已经实现。

## Purpose / Big Picture（目的与全局）

用户说过的“下周三”应始终指向说话时确定的日期，不能在几天后召回时重新解释。对同一问题短时间重复抽牌时，先返回已有牌面；用户明确坚持后才允许另建一副固定牌面。两项功能进入 P3 的工具、持久化和恢复验收，同时把新版 07 附录 B 的十二项增补放入独立 v2.2 定义，不改变已有评测执行快照。

## Context and Orientation（背景与定位）

本次分支为 `v4/p3-research-update`，从实际远端 `v4/main@7fa5e10a4dbe0e2878e28c6f6a115f17d013aaa2` 创建独立 worktree。2026-10-18 核查时 P1/P2 仍是草稿 PR，尚未合入该基底；未找到 `v4/p3-agent-runtime` 或契约 v2.1 执行目录。完整 P3 的前置条件仍为 P1、P2 经批准合并。询问用户实际任务位置的同时先完成不依赖该信息的九文档同步及独立场景定义，不擅自执行其它交付文件中的合并或调用指令。

若用户提供的实际 P3 已有 ExecPlan，本文件只是研究分支的接入说明：按增补合并 U4/U7 和冻结边界，不覆盖在途任务的 Progress、Decision Log 或已有源码。

设计依据为 `docs/v4/02_v4架构蓝图.md` §3/4/5/11/16、`docs/v4/prompts/P3_Agent循环与工具.md` 的 v4.1 增补、`docs/v4/16_算命Agent架构研究.md` U4/U7，以及 `docs/v4/07_评测场景集.md` 附录 B。源码内的运行时提示词不在本次同步范围；06 文档中的 critic 增补不能被理解为已经更改运行时版本。

复用接口以实际代码为准：当前基底 `mingjing_core/timekit/clock.py:7` 的 Clock、`:18` 的 FrozenClock 可冻结当前时刻；`mingjing_core/adapters/tarot.py:112` 的 TarotService.create_draw 已提供幂等请求、owner/subject 校验、`explicit_new` 和 `previous_draw_id`。P2 候选中的 `application/memory.py` receive/save_fact、`memory/threads.py` message_fields、`timekit/timestamps.py` history_instant 与 `timekit/now_block.py` event_at 消费路径，在前置合并后重新定位并复用，不复制一个平行存储实现。

不可改变的行为包括原话溯源、owner/subject 隔离、删除与撤销传播、原固定牌及揭牌权限、同一请求幂等、Outbox 不重发、v3 默认路由与回滚。现有同 case/stage 的旧 draw 默认复用不是一个 24 小时到期缓存；不能把新护栏实现成过期覆盖旧牌。

“说话时刻”是被引用原消息的带时区时间；“执行时刻”是工具这次运行的 Clock。二者不相等时，U4 必须使用前者。

## Progress（进度）

- [x] (2026-10-18) 核查本机与远端分支；确认当前可见状态没有 P3/v2.1，保留任务位置待澄清。
- [x] (2026-10-18) 九份大脑文档逐字节覆盖并独立提交，提交 `84a724b5eee178ac5e3722fed60dabc7d1a76cd4`。
- [x] (2026-10-18) 将 U4/U7 的应用服务接线、恢复不变量和验收矩阵纳入本计划。
- [x] (2026-10-18) 独立保存十二个 v2.2 扩展：12/12 严格 schema 与数据完整性通过，19 步骤、31 条合成消息，24 个坏数据定义拒绝；未连接模型或 P3 靶标。
- [ ] 定位用户所指的在途 P3 与 v2.1 执行快照；锁定其目录、提交、契约配置和原有指纹。
- [ ] 前置合并后在 `v4/p3-agent-runtime` 实现工具循环、上下文、步骤日志、调度、信封和路由；本次未实现这些模块。
- [ ] U4 在 memory_write/schedule_followup 真实写入路径落地，完成至少 20 正例与 20 反例及隔离 PG 验证。
- [ ] U7 在 tarot_start 真实工具路径落地，完成重复、坚持、边界、并发、恢复与固定牌验证。
- [ ] 新 P3 靶标运行 v2.2 扩展；单独报告，待父契约 v2.1 明确后冻结完整 v2.2 契约。

## Surprises & Discoveries（意外发现）

当前仓库与用户所述“正在进行的 P3/v2.1”不一致。远端仅存在昨夜 P1/P2/P8/P10，P1 评测源码实际常量是 `deterministic-eval-v2.0.0`。因此不能把现有 c2 重新标注成 v2.1，也不能假设已经获得今日计划的执行状态。

旧 runner 的 `_source_digest()` 递归哈希 `tools/eval/*.py`、Core 源码和锁文件。在该目录新增 Python 文件也会破坏后续恢复指纹。v2.2 定义使用相邻的 `tools/eval_v22/`；本次不更改旧 runner、schema、rubric、八十份场景或报告。

P2 save_fact 尚未提供 U4 的 event_at/said_at 写入参数，不能只给模型一句日期提示就声称完成。现有塔罗在同 case/stage 默认复用旧 draw，U7 必须额外覆盖换 case/渠道的重复请求，而不删掉旧幂等契约。旧 TA03 首次要求重抽就允许新牌，与 U7 的先回看规则有差异；保持旧 TA03 冻结，用 v2.2 AX02 验证新规则。

## Decision Log（决策记录）

2026-10-18，Codex：只原样同步用户列出的九份文件，并放在单独提交。交付文档中的其它待办只作为背景，不自动扩展为合并或真实模型调用授权。

2026-10-18，Codex：U4 解析输入必须包含原消息 ID、said_at、owner 时区和原始说法。不能使用 intake 程序时刻或执行 Clock 替代原消息时刻；无法确定消息时间/日期语义时返回 needs_confirmation，未确认前不写一个猜测日期。此项直接落实设计，不需要另定产品规则。

2026-10-18，Codex：U7 的“明确坚持”必须由用户新消息的可核验来源支持，不能由模型单独提交布尔值绕过护栏。问题相似度阈值、24 小时精确边界和确认有效期尚无完整产品口径，记录待大脑确认；本计划不在数据定义阶段私定运行默认值。

2026-10-18，Codex：v2.2 目前是十二项扩展定义，父 v2.1 未找到，不能伪造父指纹或称为已冻结的完整九十二场景契约。场景定义校验与真实业务行为验证分别报告。

## Outcomes & Retrospective（结果与复盘）

九文档独立提交已完成；U4/U7 已纳入 P3 实施和验收计划，代码尚未接入，因为可见仓库没有满足前置条件的 P3 运行时。十二个场景定义、19 步骤、31 条合成消息通过离线定义校验；24 项坏数据定义拒绝、UTC 等价瞬时可接受。证据为 `docs/v4/evidence/P3/research-update/v22-data-validation.json`。二十四项是数据/schema 反例，不是 U4 所要求的二十正例/二十反例业务测试。业务测试、P3 阶段验收和真实模型得分不能由本次文档/数据校验推导。

## Plan of Work（工作计划）

P3 主体仍按阶段提示词实施：先建立 ModelPort 工具循环和步骤日志，再做 ContextEngine、工具集、两通道调度、core4.0 信封与按 owner 路由。ask_user 结束当前轮，下一条用户消息新起一轮，不实现 interrupt/resume；只读工具可并行，写工具串行；危机模式隐藏命理与塔罗；提交保留撤销与版本闸门。所有写操作使用稳定 run/epoch/step operation_id。

U4 作为 memory_write 与 schedule_followup 的共同应用服务：先读取有权限的原消息，保留原始时间和 SourceRef.quote；按 owner ZoneInfo 解释日期，输出归一化 event_at、said_at、原始说法和是否需确认。said_at 及含具体时分的 event_at 按 UTC 存储，另保留 owner 时区与原始说法；只有日期的 event_at 保留 YYYY-MM-DD 及日期粒度，不擅自补成午夜。确认后在同一原话授权/幂等事务中持久化。工具仅调用应用服务，不直接写 SQL。以后召回使用已有 event_at，不以新的 today 再解析旧相对表达。

U7 在 tarot_start 的应用层执行：同 owner/subject 查询最近相关问题，匹配规范化文本及经裁定的相似度规则；检查与建牌处于同一事务或等价串行边界。重复且没有可核验坚持消息时返回 recent_draw_exists 和已有 draw ID，新增牌数为零。确认坚持后调用原 create_draw 的 explicit_new/previous_draw_id 路径；旧牌、正逆位与解读版本均保持。重放原请求仍返回原结果，不消耗新随机抽牌。

原 create_draw 还要求 previous_draw_id 与新请求属于同 subject、同 case。跨 case 命中已有牌时不得直接传入该 ID 来绕过校验；确认后沿用原 case 还是保留新 case 并另记关联，要在 P3 工具契约中明确，当前阶段不改变旧校验。

## Concrete Steps（具体步骤）

在独立研究 worktree 执行文档/场景静态校验，并保存路径、字节摘要和旧评测未变证据。开始真实 P3 代码前先核实父提交与用户提供的在途任务位置，再读取完整相关函数与调用方并更新行号。不得在基线工作树里追加 Core 源码。

后续 P3 业务验证需在独立 Core/Charts 环境与可丢弃 PG15 上执行：

    python -m pytest tests/v4/agent -q
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted

v2.2 新场景不能直接传给旧 schema/runner；其 ID/category 白名单是冻结契约的一部分。未来 v2.2 入口明确绑定父契约和 P3 靶标后才执行完整契约。

## Validation and Acceptance（验证与验收）

U4 正反例各至少二十项，以 2026-10-17 周六为基准，覆盖两个工具、owner 时区跨日、月底/跨月/跨年/闰日、相对日期与明确绝对日期、无日期、引用和否定/条件表达、时间缺失/非法输入、歧义确认。确定例包括周六“下周三”→10/21、“月底”→10/31、“过两天”→10/19。周日“下周三”按设计返回 needs_confirmation，不偷偷选一周。负例不能写入猜测 event_at。

TM01 必须先在10/15收到“下周三面试”，真实执行写入，核 event_at=10/21、said_at=原消息时间和原话；推进到10/17再问时回答还有四天。TM02 从9/30“月底交房租”的真实写入开始，再到10/17召回；只能确认指向9月底，不能编造已交状态。不能用预置绝对日期替代上述写入检查。

U7 覆盖规范化相同、高度相似与不同问题、窗口内/边界/窗口外、跨渠道/换case、owner/subject 隔离、已删除 draw、没有坚持来源及有明确坚持来源、并发请求、崩溃后重放。AX02 第一次重复请求应返回已有ID且draw计数不变；第二条明确坚持消息后才新增一个draw，原牌逐字段不变。既有 case/stage 复用和删除传播测试保持通过。AX01 的第三次焦虑性重复询问应转向可控行动，不再占卜。

十二个附录 B ID 为 A01–A03、MS01–MS03、KU01–KU02、TM01–TM02、AX01–AX02。跨会话场景必须有不同 conversation_id，不能把同线程连续两条消息当跨会话验证。当前只验证定义的完整性，未验证 P3 业务通过率。

## Idempotence and Recovery（幂等与恢复）

本次无数据库迁移、配置切换或运行时写入。回滚时回退独立文档提交和扩展定义提交，不接触冻结基线。后续 U4 重放必须复用同一原消息、绝对日期及 operation_id；U7 重放同一请求不再创建牌阵。崩溃续跑与取消必须遵循 P3 journal/lease，不绕过旧牌删除和撤销账本。

## Artifacts and Notes（产物与备注）

九文件复制证据、旧评测冻结摘要、十二场景静态校验与回执放 `docs/v4/evidence/P3/research-update/`。单独提交的九文件与大脑源逐字节一致；所有新增场景使用合成输入，不含用户资料。

## Interfaces and Dependencies（接口与依赖）

本次没有新增生产接口、数据库迁移或依赖。未来 U4 应以现有工具 ToolResult 返回 needs_confirmation，并由 ask_user 结束本轮；U7 重复结果返回 recent_draw_exists 和 existing_draw_id。实际参数/持久化实体必须在已合并 P1/P2 的 P3 工具契约中定义，不能通过此计划假定接口已经存在。

## 修订记录

- 2026-10-18：建立研究增补接入计划，明确 U4/U7 的真实写入、来源时间、幂等与固定牌验收；记录可见仓库缺少在途 P3/v2.1，防止误改冻结执行源。
