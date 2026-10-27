# P4 M5：事件正文期限与精确删除证明

本 ExecPlan 遵循 `.agent/PLANS.md`。创建于 **2026-10-21 11:05:18 +08:00**，由工具 UTC 换算北京时间。工作树为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，只读基准 HEAD 为 `a1270174e6f64cfe1abe915a09836647c1da3484`。本片仅交设计与新增、未运行的回归源码；生产修改和 pytest 均须 root 二审后另行分配。

## Purpose / Big Picture

已提交运行的流式正文在 24 小时后真正删除，其他健康事件在 30 天后删除，已提交答案仍从正常 run/history 入口读取。删除不能让序号重新使用，也不能让订阅器从最终答案重新生成已过期的事件正文。24 小时至 30 天之间，曾经确实存在且由清理事务删除的游标仍可证明；从未存在或不明原因丢失的游标继续拒绝。撤销和无痕退役立即擦正文、保留原元数据行的旧保护必须保持。期限、删除证明和内部水位均不进入公开 events_v1 Schema。

## Context and Orientation

复用的现有函数（路径均相对于上述工作树）：`repositories/run_event_log.py:65 append_event` 是唯一事件 INSERT，调用方已有 owner/run 事务和写栅栏；`application/run_event_read.py:40 validate_cursor` 核当前 owner/run 精确行，`:56 ensure_terminal` 修复无证明丢失的终态事件；`application/privacy_maintenance.py:19 tick` 目前只处理临时线程、提醒和 30 天步骤；`repositories/privacy_foundation.py:119 clear_runtime_outputs`、`application/private_retention.py:68 _scrub_runs` 立即置事件 payload 为 `{}` 并留元数据；`repositories/postgres.py:289 invalidate_derived` 负责撤销闭包，`:548 prepare_retry` 保留 usage。`application/agent_finalization.py:108 finalize` 在同事务提交最终答案，但未持久化不可变的专属提交时间锚。

已完整阅读 P4 提示词、蓝图相关隐私/流式章节、28 号第三节冻结 v1、现有读写/撤销/终态源码、0005 表定义和相关旧测试。P4 的 24 小时是**运行提交之后**，不是事件创建之后。0005 的 `core_run_events` 为 PK(run_id,seq)，没有墓碑表；已有 `core_runs.usage` 可存内部元数据。墓碑指不含正文、能证明某个准确序号曾被可信清理删除的记录；高水位指该运行曾分配的最大序号，两者不能混为授权。

## Progress

- [x] (2026-10-21 11:05:18 +08:00) 完整读现有实现与旧保护；确认五处静态缺口及 core_operations 存储语义。
- [x] (2026-10-21 11:05:18 +08:00) root 允许精确实际删行证明优先；本片保持只新增计划/红例源码、0 pytest、0 生产修改。
- [x] (2026-10-21 11:08:59 +08:00) 新红例初版完成静态 Ruff/format/AST 检查；7 个测试函数（当时8个参数例），0 collection/pytest/PG。随后补 stale 新 epoch 参数与不可复用旧 commit 操作时间的设计确证，最终静态复核另记。
- [x] (2026-10-21 11:10:27 +08:00) 最终新增源码 Ruff/format/AST 静态复核通过：239行、最长函数23行、最长行101字符，7函数/9参数例；0 collection/pytest/PG，冻结两新文件交审。
- [x] (2026-10-21 11:12:58 +08:00) root批准实施及独立归档首红；精确a1270174/tree a1bc4137加原9例，真实PG 4 failed/5 passed/6.47s，四缺口均重现，不改共享树回测。
- [x] (2026-10-21 11:20:38 +08:00) 显式手动sweep、真实终态锚、独立kind墓碑、水位、30d关闭与读门实施；新26 passed/11.33s。第一轮8绿1红是撤销未提交运行没有锚的fixture错误，修新时钟观察方法、不改旧断言。
- [x] (2026-10-21 11:21:41 +08:00) 8个明确旧文件51 passed/24.85s；原保护及断言逐字未改，0skip/xfail/warning。
- [x] (2026-10-21 11:24:10 +08:00) 补候选筛选饿死和closed失败/过期重试拒绝：3 passed/1.45s；总计29新+51旧独立通过。本次不是最终头全量/CI，按root指令不重复无变化目标。
- [ ] root审查/提交/推送及新精确头CI；后台小时任务保持默认未接线。跨进程清理压力、真实线上期限与未知legacy提交锚仍未验证。

## Surprises & Discoveries

`PrivacyMaintenance.tick` 没有事件清理分支；目前即使明确手动调用，也不会删除 24 小时正文或 30 天事件。`append_event` 仅按剩余行的 `max(seq)+1` 分配，删尾或删空后可能重用序号。`validate_cursor` 非零只接受实际行，所以朴素物理 DELETE 会把合法旧游标变成未知游标。成功终态缺 final 时 `ensure_terminal` 会按 run.result 再造；失败终态的 `event_terminal_error` 指向被删行时会报损坏，均不能把正常清理与损坏混用。

全仓源码/SQL检索没有发现删除或按期限清理 `core_operations` 的现有路径。其表为 PK(owner,operation_id)，字段 `fingerprint/kind/result_id/created_at` 均非空，result_id 为 text，无实体外键，**没有 result 或 JSON 列**。规范白名单元数据只能编码进 result_id 文本并严格解析。通用 `_operation` 要求 fingerprint、kind、result_id 全相等；事件幂等专用 kind 为 `run_event_v1`；事项/自写证明另按真实 kind 过滤。新墓碑必须用独立 kind/命名空间，绝不复用 run_event_v1、case、实体 kind 或已有回执。部署已有运行角色对该表的 CRUD 权限可复用，不新增授权；新 kind 不能传给 repo.put 的实体注册入口。既有表可承载精确证明，但不是带签名的防数据库管理员伪造凭证；仍以受信 PG 写事务为权威。

现有终态只有会变化的 updated_at；检查点、重试、撤销均可能改变它。事件 created_at 又可能晚于答案提交。两者均不能冒充精确提交锚。新红例用刚完成运行的 updated_at 仅定位旧实现的时钟测试窗口，不把它宣称为生产可用的不可变锚；实施时应改为读取新增可信锚，观察性断言不变。

追加静态确证：Journal 的 finished_at 仅代表 model/tool 完成，发生在评审与 AgentFinalizer.finalize 之前，没有提交步骤，故不可复用。`memory/threads.py::_persist_assistant` 的 `assistant:<run>:<fingerprint(value)>` 操作、`application/threads.py::_record_private_reply` 的 `private-assistant:<run>` 确实通常在 finalizer 同事务创建；但两个路径均可能复用旧 assistant 并直接返回，不创建新 operation，且这些 ID 没有 attempt/epoch。其 created_at 不能无条件证明本次终态转移时间。若做 legacy 证明必须另核精确消息/operation/epoch、排除重用；当前设计不自动 bootstrap 此猜测。

## Decision Log

2026-10-21 11:05 / root：首片只设计及新红例源码；11:10之后二审明确授权2新生产文件及6个最小接点，后在M4a释放第4槽时授权独立基线首红与明确目标链。Schema、旧迁移、b9、web/static及并行M4/joint不归本片。后台默认不开，本周不合v4/main/main。

2026-10-21 11:05 / root：不接受以 min/max 范围证明精确游标，也不接受 usage 中无界增长的区间数组。采用候选的 core_operations 专用 body-free 精确墓碑；24h–30d 可续传，30d 后统一拒绝过期事件历史、改从 GET run/history 取已提交答案。旧无证明丢 final 的恢复断言仍有效。

已实施：`EventRetentionSweep.tick(limit=50,event_limit=1000)`默认没有构造、启动或定时注册。原9例基线act为真实现存PrivacyMaintenance.tick，证明旧手动维护入口缺能力。获批后仅改**新测试**act为显式新服务、时钟helper读取真正terminal锚；撤销未提交运行不制造锚，捕获Clock作为观察窗口。观察性断言未放宽，原测试断言未变，后台未接线。

2026-10-21 11:23 / root：可信30d closed失败/stale运行的恢复**保守拒绝**，固定中文“事件历史已过期，请明确发起新请求”，零状态/预算/epoch变化，不自动新建请求、不重开事件/Journal。未来是否允许清洁新epoch属于待大脑产品取舍；当前不等答复。未closed正常失败重试仍清旧锚/保留HWM，旧无证明缺原件门不变。

候选筛选追加到期条件，避免排序靠前但尚未24h的运行占满limit而饿死已经到期的运行；同事务仍重新核scope/epoch/status/lease，不把筛选当授权。M4b获root许可只读复用纯`is_closed(run)`接口，不移交本片写权限。

## Plan of Work

第一步已实现可信终态锚与水位。内部 `usage.event_retention_v1` 存版本、单调水位、attempt/epoch/status终态锚、常量级关闭/清理完成信息和scope指纹。AgentFinalizer成功、repo.fail_run失败/停止及queued取消在原run事务记录锚；原撤销/无痕擦除路径不改。重试开始新attempt/epoch时旧锚不能清新运行。每次append锁当前run，以实际最大值和持久水位较大者加一，同事务写回，拒bigint溢出。无水位旧运行首次可信写入只可从实际行初始化，不能恢复升级前无记录的丢失尾行；此历史边界未宣称解决，已知稳定operation原件缺失仍按旧门拒绝。无可信提交锚的legacy终态保守跳过并计数，不猜updated_at。

第二步是精确删除。新sweep在短事务中FOR UPDATE SKIP LOCKED锁run，复核owner/runtime、status、attempt/epoch锚及没有lease；候选查询不授权删除。24h只选择真实非空text_delta行，每行删除和专用墓碑同事务；30d先可信关闭再有界删除健康事件/本服务墓碑，失败全回滚。ID固定前缀+run身份哈希+seq，kind=run_event_retention_v1；result_id为规范白名单（run哈希、seq、kind、epoch、attempts、删除/过期时间），fingerprint绑定同一元数据，不含正文/推理/原话。已有operation ID冲突则整批拒绝，不覆盖或转解释其他回执；attest还重查实际owner/run/seq非空正文行，不能调用方自报证明。

第三步是读兼容。24 小时到 30 天非零 cursor 先查原行，缺行时只能查当前 owner/run/seq 精确专用墓碑；必须同时核 kind、字段结构、指纹和未过期锚。高水位只防重用，不授权 cursor。30 天到期在同事务关闭该已完成 attempt/epoch 的事件历史，删除健康事件和本片旧墓碑；关闭证明保留在 run 内，读入口返回固定过期错误或起点空终态，不返回新公开字段。`ensure_terminal` 仅遇匹配的可信关闭证明时停止再造；没有该证明的手工丢 final 仍按旧断言修复，损坏/擦除原件仍拒绝覆盖。

第四步是隐私优先。撤销/无痕退役已经 `{}` 的原元数据行保留，不借 24h/30d 清理重新序列化或还原。其正文和步骤继续立即擦除；重放旧稳定 operation 永远不能从墓碑补回 payload。已关历史之后撤销不能借新 status/updated_at 重新开流或造含正文 final。私密线程24h退役仍走旧服务；新 sweep 不扩大读线程权限。

## Interfaces and Dependencies / 待 root 分配的最小接点

已新增`application/event_retention.py`（显式有界sweep）及`repositories/event_retention_metadata.py`（精确墓碑/水位/关闭门），均≤400行、函数≤60行。root已逐一释放下述6个最小接点；成功/失败/queued取消写锚，撤销/无痕沿原擦除元数据路径，不为未提交撤销运行补造锚。

`core_operations`无原TTL清理；仅按专用kind+精确run哈希命名空间在30d事务删除**本服务自己的墓碑**，不删run_event_v1或其他效果回执。元数据规范编码在result_id TEXT，精确核scope/hash/seq/kind/结构/时间/指纹；不是不存在的result字段。usage为常量大小，不存删除数组。closed旧失败重试固定拒绝，不重开；未closed重试清旧锚且保留水位，旧tombstone不能按当前epoch盲升级。

实际最小接点：新`application/event_retention.py`和`repositories/event_retention_metadata.py`；既有`run_event_log.append_event`、`RuntimeEvents.send`、`RunEventReader.validate_cursor/ensure_terminal/_error/page`、`AgentFinalizer.finalize`、`PostgresRepository.fail_run/prepare_retry`、`DispatcherCancellation.request`。读分页把终态检查与取行置同一个run锁事务，避免清理在两者之间关闭历史却仍读出剩余正文；_error用当前usage合并，避免覆盖新持久水位。Finalizer透传自己受信Clock，其他锚用全局Clock；不会依赖本机Tokyo时区。

公开事件 Schema、TS 类型、HTTP 路由、数据库表/列、依赖和旧迁移均不变；不占用为 P5b 预留的 0009。小时调度的默认关闭配置和接线另片审查，不能把已有每分钟 MaintenanceSchedule 静默变成自动删除入口。

## Validation and Acceptance

新增 `tests/v4/streaming_integration/test_event_retention_pg.py` 使用真实隔离 PG fixture、ScriptedPort 和冻结 UTC 时钟；外部 HTTP/子进程禁止。当前仅源码，连 collection 都未执行。7 个函数共9个参数例：静态预期4个暴露现缺口、5个保留边界；这些不是实际红/绿数字。待批准的可观察验收：23h59m59s 正文存在；24h+1s 正文实际行不存在而其他事件及已提交答案不变；30d+1s 其他健康事件也不存在，反复 page/ensure_terminal 不再造 final；撤销后的原 seq/kind 行留下且 payload={}；物理删尾后重试新 seq 大于曾发最大值；实际清理删行的精确游标合法，清理前手工空洞仍固定拒绝；running/queued、failed同epoch重试及stale新epoch不能被旧锚清理。

旧断言保留：`test_event_notify_pg.py::test_missing_or_privacy_cleared_original_is_never_reconstructed` 禁止补造缺失/擦除幂等原件；`test_run_event_replay_pg.py::test_subscriber_and_runtime_emit_one_final_and_one_question` 仍修复**无正常清理证明**的丢失 final/ask；同文件损坏 final 不能覆盖；`test_event_cursor_pg.py` 的未知洞、跨 owner/run、无副作用拒绝及撤销合法元数据行全部不改。新删除证明不扩权限、不绕 ScopeError、不把未知洞视为丢包。

映射 `07_评测场景集.md`：F03 删除原话应清理运行事件；F04 撤销/重生成 epoch 不混；X03 恢复不重复效果与序号；X04 活跃取消不被清理抢跑；X08 合法续传无重发/缺漏。新 TTL 场景是这些保护的补充，不声称本片运行了原评测或修复已有 X03 分歧。

## Concrete Steps

静态检查执行目录为上述P4工作树，9个正常格式生产/新测试文件通过Ruff/format；postgres.py仅11行局部差异、不整体重排旧文件：

    python -m ruff check tests/v4/streaming_integration/test_event_retention_pg.py --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check tests/v4/streaming_integration/test_event_retention_pg.py

已获二审与单一窄槽后，独立基线保真实首红、实现后新26、8旧文件51、最后3边界串行执行，详情见证据。每轮runner清凭据/PG隐式配置、关闭追踪与飞书，CORE_TEST_DSN只本机隔离PG随机schema；无并行第二pytest、未启动全目录回归、未改旧期望/xfail。原基线首次创建空目录后发现共享HEAD前移，断言退出无其他副作用；之后显式archive已审a127，不复用该空目录，也不改root正在跑的11点归档。

## Idempotence and Recovery

清理事务同时保存水位/墓碑/关闭证明并删除实际行，任一 SQL 失败回滚本批，不能留下假墓碑或先删后写证明。多进程用 run 行锁互斥并 SKIP LOCKED 跳过忙 run；每次真正删除前再核最新 epoch/status/lease。重试/取消同样拿 run 锁，因此先重试时 sweep 看见 queued/running 必须跳过，先清理时 retry 只能在保留水位和正确历史关闭状态后继续。

真实隐私删除不可回滚恢复正文；恢复仅指事务失败时原行和证明都仍在，重新运行同一清理稳定幂等。不为排障从最终答案重建过期 SSE，不备份或导出私人正文。测试直接 SQL 删除是合成故障注入，不是允许的生产清理路径。

## Outcomes & Retrospective

当前手动清理已实际通过29新+51旧分片目标；原9例基线真实4红5绿留存。24h物理删除/精确墓碑、30d关闭不再造、序号水位、queued取消/失败/成功同事务锚、scope/fp防篡改、锁/回滚和正常重试保护均有真实隔离PG观察。默认后台仍未接线，未知legacy锚保守跳过；升级前无记录丢尾无法恢复，closed旧失败恢复的产品取舍待大脑。新精确头CI、完整P4/旧DOM、真实模型与线上TTL未验证；本片所有真实模型/外发/服务器访问0。

## Artifacts and Notes

本片独占为上述8生产文件、2新测试、本计划及`docs/v4/evidence/P4/2026-10-21-event-retention.md`。并行M4/joint、web/static、公开Schema、b9和旧迁移未改。证据保留真实首红、首轮fixture失误及后续绿结果，不把分片通过冒称最终头全量/CI；root统一stage/commit/push，本代理不git add。

## 修订记录

2026-10-21 11:05:18 +08:00 创建。列实际缺口、专用 operations 精确证明候选、旧断言保护、未运行红例与待审批生产范围；按 root 要求 0 pytest、后台默认关闭。

2026-10-21 11:08:59 +08:00 记录首次静态通过；根据 root 追问，补实际 result_id TEXT 编码/权限/隔离 kind 说明，以及 Journal/assistant operation 时间不能直接证明当前提交的源码确证；未运行 pytest。

2026-10-21 11:10:27 +08:00 记录最终静态检查与两文件冻结，补9参数例含同epoch及新epoch排队保护；交 root 二审，不执行测试或生产修改。

2026-10-21 11:24:51 +08:00 按root二审实施并补真实红绿、首轮fixture修正、29新+51旧与knownlegacy/closed重试边界；清理默认手动，准备12件冻结交审。
