# MOD：验证旧流式 Outbox 恢复与能力边界

本计划遵循 `.agent/PLANS.md`。所有记录为北京时间。新增独立测试、计划与新证据；root仅修本轮已新增的stream_outbox_v2/contracts.py，不修改启动基底既有文件、原测试或黄金。

## Purpose / Big Picture

流式卡片意图描述拟执行的外部操作，租约是某个 worker 在限定时间内操作该意图的能力。
本轮补验崩溃恢复、租约续期和来源变化的组合：尚未发送的操作可以明确恢复，已发送但结果未知的操作必须保持未知。
用户不应因旧 worker、迟到回执或新操作编号而收到重复卡片。所有输入显式虚构，不连接实际平台。

## Context and Orientation

工作目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
复用 `mingjing_core/adapters/channels/stream_outbox_v2/codec.py` 的 `state_metadata`、`restore_state`，
`intents.py` 的 `prepare_intent`、`next_intent`、`fallback_intent`，`transitions.py` 的 claim、
begin_dispatch、renew、acknowledge、reject、mark_uncertain、recover_expired、reconcile，
`freshness.py` 的 FreshnessEvidence/VersionEvidence 和 `guards.py` 的 CAS/租约/回执绑定规则。
同时复用 CardCheckpoint 公开契约与 Clock；不使用 object.__new__ 或篡改冻结 dataclass 绕构造守卫。
冻结依据为蓝图 §16 的 Outbox 送达不明不自动重发、大脑 28 号模块线第 6 项和
`docs/v4/integration/mod/Q6_p9_v2_20261021.md` 的双 freshness 与 host CAS 接线要求。

## Progress

- [x] (2026-10-21 09:07 +08:00) 读取指令板 v1、7 个产品文件、旧 P9 v2 契约/测试、官方 P9 新增 legacy 守卫和历史覆盖。
- [x] (2026-10-21 09:08 +08:00) root 明确通知性能实验结束，允许新增独立测试和单 pytest；此前未创建测试或运行测量。
- [x] (2026-10-21 09:08 +08:00) 向 root 发送独立行为选择与真实接线风险；新增唯一 helper 与三份目标测试。
- [x] (2026-10-21 09:18 +08:00) root 修复历史序号一致性后，原 127 目标全部通过/0.29s，无排除或真值改动。
- [x] (2026-10-21 09:19 +08:00) root 授权两个 P9 兼容套件 scoped 覆盖，1955 passed/25.63s，7 产品及 35 测试/fixture 前后 SHA 一致。
- [x] (2026-10-21 09:20 +08:00) 冻结 4 个新增测试/helper、原失败证据、验证和覆盖报告；分支覆盖 85.3659% 未达 90%，保留后续。

## Surprises & Discoveries

DAY 报告是较早快照；之后官方 P9 下的 legacy_freshness 守卫已覆盖不少 codec/intents 拒绝分支。
不能把 DAY 未覆盖直接当作当前缺陷，也不重复原 98 项以虚增验收数量。
现有恢复测试主要覆盖 dispatched→uncertain，需独立补 leased 恢复仍只持原 hashed 能力、
续租后的旧 revision 拒绝和 unknown 在全部公开能力入口均不可重新发送。
确认最小反例：公开生命周期 update1 已 ack → update2 prepared，持久化 history 的已 ack 序号
改为 3，而当前 reserved=2；restore_state 仍接受，独立真值要求受控拒绝。目标测试 1 failed/0.21s，
已立即通知 root，未修改产品。失败证据为 `STREAM_OUTBOX_history_sequence_failure_20261021.json`，
SHA-256 `469e170374455c020a62ea753e461d3ba3f20c0a436e22757d3318edf9a630e5`。
其余首批目标在排除三个已知历史序号节点时 121 passed/3 deselected，0.28s；不是完整通过。
随后新增两个历史逆序/重复序号反例及一个明确拒绝后合法序号空洞正例。root 统一修复 history
已知序号严格递增且早于当前 reserved、acked 历史不超过 last_acked，不要求连续或完整前缀。
所有 127 项原真值均通过，合法拒绝空洞和 checkpoint 空历史仍接受。

## Decision Log

2026-10-21 09:17 +08:00：两组先固定真值并保留真实失败（1项最小失败、独立23项10失败/13正例通过）后，
root完整阅读codec/contracts/intents/transitions及调用方，只在本轮新增contracts构造校验增加已知历史序号检查。
历史中的update/close序号须严格增加且早于当前；acked历史不能超过last_acked。无完整前缀、拒绝空洞和checkpoint接续仍合法。
不增加连续性或完整历史证明，不改序号分配、unknown/回执/双freshness/租约/CAS。坏快照受控拒绝，host不能丢账重建新意图。

先锁定行为，再执行产品。不通过伪造内部不可能状态来执行重复的二次守卫。
metadata 的 scope hash 是一致性标识，不能认证 PG 持久化或抵抗有权重写整份 metadata 的 host；
测试只断言已冻结 scope 与传入 scope 不一致时拒绝，不把普通 hash 当作签名。
freshness 投影仅可信 host 可构造，纯模块核对一致性；完整有效投影不能冒充实际查询了来源账本。
恢复 leased 状态不代表新 worker 自动获得原 token，也不允许恢复 dispatched 为 prepared。
旧 API 的已结算同 operation 重放是 no-op，不擅自把它改成必须报错。

## Outcomes & Retrospective

真实历史序号恢复缺陷已经原样保留并由 root 修复；与初始失败时的 7 源哈希比较，只有 contracts.py 变化。
127 独立目标及 1955 P9 兼容目标通过。source 只统计七产品：行 492/528=93.1818%，
分支 210/246=85.3659%，综合 702/774=90.6977%。分支尚未达到 90%，不能宣称全部覆盖目标完成。
codec 中多处二次状态守卫受构造守卫先行约束，没有用绕构造的假对象刷覆盖；其他未执行分支和完整 core3
合法 freshness 路径保留后续。DAY 历史较早，不能把官方 legacy 测试的既有覆盖收益全归本 127 项。
本子任务未编辑产品；没有数据库、业务或外部变化。主线真实 PG/网络接线及 CI 仍未验证。

## Plan of Work

新增 `tests/v4/p9_v2/coverage_support_acceptance_mod.py`，独立构造虚构完整 core4 结果、来源/依赖投影和公开生命周期，
使用显式命名空间导入，避免旧 bare helper 收集问题。
新增 `test_recovery_coverage_acceptance_mod.py`，验证所有合法阶段 roundtrip、leased 恢复 token/期限、
dispatched 恢复永久 unknown、历史/序列/远端身份被篡改时受控拒绝。
新增 `test_capability_coverage_acceptance_mod.py`，验证续租严格延长、旧 CAS/fence/token 无法 ack/reject/发起新 dispatch，
租约期限上下界、未知状态全部入口、七字段 scope 对账，以及无明确拒绝就不产生 fallback。
新增 `test_freshness_coverage_acceptance_mod.py`，验证领取成功后来源/依赖/epoch 改变仍阻止发送，
reclaim 后旧证明不能复用；覆盖完整结果与 manifest 构造的真实非法形状，严格核对真 bool/int。

## Concrete Steps

目标测试在本目录、Core 解释器 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe` 运行。
provider keys 在当前测试进程清除、tracing 关闭、socket 禁止；TEMP/TMP 指向本树 `private/mod-week/tmp`。

    python -m pytest tests/v4/p9_v2/test_recovery_coverage_acceptance_mod.py tests/v4/p9_v2/test_capability_coverage_acceptance_mod.py tests/v4/p9_v2/test_freshness_coverage_acceptance_mod.py -q --tb=short

每 agent 同时最多一个测试进程。不启动全量或自行安排覆盖/性能测量；需要 scoped 覆盖时先与 root 协调。

## Validation and Acceptance

对应 `07_评测场景集.md` 的 X08 核心续写意图，以及 F03 来源失效扩展约束；纯计划并不证明实际撤销删除或投递。
恢复 leased 的有效原能力仍遵守期限与双 freshness；旧 token/fence/revision 不得借续租或重领复活。
dispatched、崩溃和不明结果只进入 uncertain；即使时间过去一年、来源重新有效或换 operation，也不能自动重发。
对账必须有完整绑定、真布尔 delivered 和明确 evidence_ref，拒绝外 owner/subject/outbox/run/business/channel/target。
同卡 update/close 继续预留下一序号；只有明确拒绝的 close 才产生独立 fallback 意图。
模型、网络、PG、业务和通知请求均为 0；真实失败不能通过修改期望变绿。

## Idempotence and Recovery

测试只创建进程内不可变状态，可重复运行。失败证据写新文件，保留原断言和源码哈希；产品修复由 root 独占。
不修改原 P9 v2、官方 P9 冻结测试或黄金材料，不读 Q5 B 或校准 75 条正文。

## Artifacts and Notes

本计划为当前断点：测试、失败/修复/兼容证据和回执均已冻结，待 root 独立提交；分支覆盖不足保留储备。
历史依据 `docs/v4/evidence/MOD_2026-10-21/DAY_new_code_coverage.json` 保持只读。
新的验证结果预计写入 `docs/v4/evidence/MOD_2026-10-21/STREAM_OUTBOX_boundary_*`；未运行前不写通过结果。
实际覆盖报告 SHA-256：`d13357cbc8365eb8232b40155bf81f7f2e408ef41dda6fb9d9de7711d96f162f`。
验证报告 SHA-256：`f393cd010ab35680d764b608c1bf81a996fd61304b2791b7eaa9f06602a4222c`。
报告包含每文件 missing_lines/branches、实际命令、北京时间及来源身份。原失败 JSON 不覆盖。

## Interfaces and Dependencies

没有新增产品接口、Schema、锁文件、运行配置或数据库迁移。旧 API 的版本/fence/来源证据不变量保持。
host 必须实际锁行、核验成功 run 与当前来源、持久化 dispatched 后才调用外部传输；这些仍不能被纯函数认证。

## 修订记录

- 2026-10-21 09:08 +08:00：创建，只读审阅后冻结行为选择，记录已获测试闸门与未完成断点。
- 2026-10-21 09:14 +08:00：记录最小真实失败及其余 121 项通过，补充单调历史反例与合法空洞正例；等待 root 产品修复，仍未完成。
- 2026-10-21 09:20 +08:00：记录 root 修复后 127/1955 通过与实际覆盖，冻结本轮；分支覆盖不足不隐瞒。
