# P3 M5：在原话入站前识别自然语言无痕

本 ExecPlan 遵循 .agent/PLANS.md。术语“自动模式”表示当前认证用户在当前 channel/conversation 的后续消息路由；不是模型自行推断的隐私等级。工作树 C:/Users/Administrator/Documents/Codex/zhiming-v4，分支 v4/p3-agent-runtime。复用 application/threads.py:create/get/receive、private_retention.py:retire_private_thread、thread_queue.py:owner_runtime、repositories/postgres.py:transaction/put/get/fetch_run；不得改变 owner/subject 隔离、来源不跨线程移动、撤销不复活和私密长期禁写契约。

## Purpose / Big Picture

蓝图 §4、P3 M5 要求网页和飞书中的直接“开个无痕/这段别记”在持久原话前进入临时线程，后续沿用到明确“结束无痕”或24小时无活动。引用、假设和他人转述不构成当前用户的模式指令。旧 run 正在运行时收到“本轮别记”，应立即阻断其后续长期写，不能只过滤这条补充本身。

## Progress

- [x] (2026-10-21 00:45 +08:00) 核对蓝图 §4、P3 M5、记忆 optout 规则及入站/API/清理真实调用方，向 root 与入口代理报接口。
- [x] (2026-10-21 00:56 +08:00) 新增严格规则、自动模式/固定事件路由收据和 run 级禁写闸门，真实隔离 PG 验证。
- [x] (2026-10-21 00:56 +08:00) root 提交原 M5 后最小接 ThreadIngress/FeishuIngress；入口代理已接 v3 安全拒绝和 private 固定重放。
- [x] (2026-10-21 00:56 +08:00) 规则/PG/Ingress/桥接/旧Gateway联合107 passed/26.49s，静态绿；证据与文件冻结交root。
- [ ] root 的工具长期副作用 barrier 接线另行验证；完整阶段 CI/脚本评测不包含在本组件结论内。

## Surprises & Discoveries

旧 v3 公共 submit 不经过 ThreadIngress，仅在新服务拒绝不足以覆盖网页旧入口；由入口代理在 route_submit 对 v3 明确隐私指令拒绝，保持原话和 run 均0。ThreadService 私密消息在单一事务里带 incognito/persist_allowed=False 提交，不能从另一条已提交 life 来源迁移；原始事件路由另有稳定收据，重放不重新触发进入/退出。

真实 PG 首轮54/56的失败来自测试未绑定外部作者，修真实binding fixture后继续；后轮77/78暴露测试用同 owner 的 create(request_id='life')跨 subject 冲突，测试与飞书 caller 改成 subject 唯一 request_id，不改变ThreadService幂等契约。飞书2.5秒缓冲旧原话在隐私控制收到时可能尚无run，故不能只挡已有run；新增 source.created_at 早于控制收据的延迟批次继承，和入队同事务提交，后来的新 life 原话不继承。

## Decision Log

自动模式按 owner/subject/channel/conversation 隔离，避免网页独立会话或飞书私聊串入他处私密。模式状态仅存线程ID，无正文。退出停止该会话自动路由，已私密线程继续既有24小时保留清理；不凭语言命令立即删除历史。显式私密 thread ID 是用户明确入口，仍经过 scope/expiry 校验。

严格规则只接受未引用的完整命令分句；命令前有假设或转述线索就不激活（可能宁可漏识别，用户可单独重发命令或用明确开关）。同消息进入/退出冲突失败关闭，不保存正文。普通 v3 保持；明确无痕或仍处自动无痕时 v3 无安全实现，先拒绝落盘，不静默回 life。

run 禁写覆盖已有 queued/running/inbox_wait 同 owner/subject/thread；所有后续长期新增/修改和任务由 root 在应用工具边界阻断。显式授权 memory_forget 保留；不删除已提交历史。闸门元数据不随 run epoch 重试清除，消费时从 PG 重读及核对入站控制收据。

自然语言“结束无痕”只退出自动模式；蓝图§4/P3 M5未要求该指令立即删除正文。API close 为明确清理入口，仍沿用既有立即退休/清理；自然退出后的旧私密 thread 保持既有TTL清理，不进入主线程L5。已有原请求重放固定其原thread/source，不重新开启已退出的自动模式；到期/已清理原请求拒绝恢复。

## Outcomes & Retrospective

本组件已实现并经真实隔离PG目标验证：107 passed/26.49s，0skip、0warning。工具执行时的长期副作用闸门由root接入并单独出证据；本组件不能替代完整P3、CI或真实供应商验收。没有服务器、真实模型、飞书发送或合并。

## Plan of Work

先新增 privacy_mode_policy、privacy_mode、privacy_run_barrier 与独立规则/PG 测试；原 M5 文件冻结期间不修改。root 释放后接 Ingress 持久化前选择真实 thread、submit 使用 source.thread_id、飞书批次按真实 thread 隔离。入口代理接 v3 public submit，root 接工具长期副作用分组。

## Concrete Steps

    $env:CORE_TEST_DSN='postgresql://core_test@127.0.0.1:55480/core_test_main'
    python -m pytest -q tests/v4/agent/test_privacy_mode_policy.py tests/v4/agent/test_privacy_mode_pg.py

联合目标验证另含 test_privacy_ingress_pg.py、test_thread_inbox_pg.py、test_feishu_ingress_pg.py、入口代理的 test_runtime_privacy_routes_pg.py 和 tests/test_core_feishu_gateway.py；结果107 passed/26.49s。

测试进程先清供应商密钥、关闭追踪；只用本机独立 schema 和冻结 UTC Clock，不依赖主机东京时区。

## Validation and Acceptance

对应评测 M04（明确别记不存）与 M13（无痕不长期保存/反思）。直接命令和普通后续进入同 private，life 历史无其正文；引用/假设/转述与“别忘记”不激活。不同 owner/subject/channel/conversation 不混用模式；固定 native event 改作者/会话/正文拒绝，退出后重放不重新开；重复不延长TTL，24小时后新普通消息回 life、过期旧重放拒绝。已有 run 的旧 usage 快照不能绕过禁写。

## Idempotence and Recovery

自动模式、路由收据、原话和 run 闸门在 owner 单事务内提交。事件路由固定并核 input fingerprint；失败回滚全体，重试原 ID 安全。无新表、迁移和依赖；不可部署或执行数据清理。

## Artifacts and Notes

证据 docs/v4/evidence/P3/2026-10-21-natural-privacy.md。3个新应用源分别204/60/84行；ThreadIngress116行、FeishuIngress238行，AST核无函数超过60行。没有新增依赖、表或迁移。

## Interfaces and Dependencies

PrivacyModeService.receive 与 ThreadIngress.receive 参数相同并返回真实 source；privacy_action(message) 返回 enter/exit/None；run_persistence_blocked(repo,run) 从真实 PG 返回可信闸门状态。后者不接受模型/HTTP 自报的模式标志。

PrivacyModeService.assert_legacy_safe(owner,subject,message,channel='web',conversation_id='shared') 在v3落原话前拒绝明确指令或仍有效自动私密，返回None表示可继续原旧验证。ThreadIngress.submit使用实际source.thread_id；queue内 inherit_source_barrier 与原 queue_run 同事务，NOTIFY不暴露未设barrier的中间态。运行的scope只取PG owner/id/subject，receipt保留指纹、线程与source ID，无私人正文。

## 修订记录

- 2026-10-21 00:45 +08:00 创建，先新增独立切片，保留原 M5 冻结文件。
- 2026-10-21 00:56 +08:00 完成模式/入站/旧批次闸门与107项真实目标验证，记录桥接与root工具接线边界。
