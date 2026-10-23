# P3：安静 HTTP 流取消的 socket 中断候选

本计划遵循 `.agent/PLANS.md`，时间均为北京时间。socket 中断指在停止本次请求时，先关闭连接的读写方向，再释放连接对象，以唤醒另一个线程里正在等待的网络读取。

## Context and Orientation

仓库根为 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。复用 `mingjing_core/models/transport.py:close_on_cancel/StreamingHTTP._request`、`tests/v4/agent/test_dispatcher_http.py` 的真实 PG+quiet HTTP 测试以及 `tools/eval/targets/v4_cancellation.py:cancel_stream`。已读根 AGENTS、README、`docs/CLOUD_DEVELOPMENT.md`；没有 models 子目录 AGENTS/README。依赖固定 httpx 0.28.1/httpcore 1.0.9，不增加依赖，不改 P1b 独立树、真实请求预算或公共事件契约，不扩大真实取消两秒上限。

## Purpose / Big Picture

P6 草稿精确 head 的 Linux CI 在真实取消后的两秒窗口失败，已经收到首个持久片段，不能解释成等待模型启动过慢。P3 与 P6 的传输和该测试代码目前相同。此片在取消/总期限时对当前 HTTP 响应先执行 shutdown，再 close，并避免外层 client watcher 抢先关闭正在读的连接。Windows 真实验证只证明本机行为；必须以精确候选提交的 GitHub Linux CI 确认 Linux 修复。

## Progress

- [x] (2026-10-21 07:44) 核对 P6 CI 完整栈、P3/P6/P1b 传输和锁定依赖源码。
- [x] (2026-10-21 07:47) 当前响应可用时最小 shutdown→close、外层 watcher 活动响应引用已实现；正常完成/MockTransport/替身头部等待保持原契约。
- [x] (2026-10-21 07:47) 14个新增模型目标与既有模型目标59 passed / 1.25s；既有真实 PG quiet HTTP、续租、X04 三项 3 passed / 3.17s，原两秒上限不变。
- [ ] 精确候选提交的 GitHub Linux CI；本机无可用 Linux 环境，不冒充 Linux 已通过。

## Surprises & Discoveries

P6 run 39466824123 的首个失败在取消后 `until(status=cancelled,timeout=2)`，启动、依赖及首片段等待已成功。P3、P6 相关 transport/dispatcher/测试代码一致；仅合并新 P3 不会凭空改变此传输行为。P1b 的 close_on_cancel 也没有 shutdown。锁定 httpcore 的 HTTP11 响应提供 network_stream 扩展；SyncStream 的 get_extra_info('socket') 返回当前实际 socket，read 调用 recv，而 close 只调用 socket.close。

## Decision Log

只在取消或总期限结束时尝试 socket shutdown(SHUT_RDWR)，正常消费完成保持普通 close。MockTransport 或没有 network_stream 的资源不猜测内部对象；继续原 close。外层 client watcher 通过当前 response 引用先中断相同响应，避免两个 watcher 竞态使 response watcher 对已经关闭的 fd 才尝试 shutdown。限定关闭当前请求连接；不改供应商配置/重试/错误消息，不修改第三方库。响应头尚未收到的真实系统读取仍沿原 client.close，此片不声称已经完成所有平台/所有网络阶段的严格两秒证明。

## Outcomes & Retrospective

候选已实现并通过本机模型与真实 PG/quiet HTTP/X04 窄目标；取消时 shutdown 先于两种 watcher 的 close，正常消费完成不 shutdown，不能取 socket 的 MockTransport 仍普通 close。当前响应资源限定在本请求，无供应商/真实消息请求。P6 的 Linux CI 失败并未被本机 Windows 结果消除，精确提交 Linux CI 仍待主协调提交后验证；也没有声称响应头未到的真实 Linux 网络阶段已经具备两秒证明。

## Plan of Work

在 transport 新增无正文日志的 shutdown 辅助函数，cancel watcher 调用它后仍执行正常资源关闭。`_request` 只额外维护当前响应引用，外层 watcher 可先关闭该响应的 socket。新增单元测试检查 shutdown-before-close、无扩展回退、外层 watcher 优先中断活动响应以及异常清理；真实本机 HTTP 流在没有后续字节时取消，要求两秒内停止且只发一次合成回环请求。

## Concrete Steps / Validation and Acceptance

只清凭据/关闭追踪并使用本机隔离 PG。运行新增模型目标、既有 stream_safety/protocols 与两个真实 quiet HTTP/X04 单例；保留测试原时间上限。对照 P3 M7 与评测 X04，必须在取消之后真实计时并保留 interrupted 片段，不能使用预先固定时间。只由主协调在允许窗口启动全量。

    python -m pytest tests/v4/models/test_socket_cancellation.py tests/v4/models/test_stream_safety.py tests/v4/models/test_protocols.py -q
    python -m pytest tests/v4/agent/test_dispatcher_http.py tests/v4/agent/test_eval_v4_pg.py::test_x04_measures_quiet_loopback_http_and_persists_interrupted_partial -q

## Idempotence and Recovery

shutdown 对重复/已关闭 socket 的预期 OSError 不输出原文；close 继续执行。取消和期限状态仍由既有 Event、领域错误和 PG 权威处理，不产生新的模型请求或重试。此片无迁移，回退候选代码即可；P1b 集成冲突需保留其中央守卫、permit 释放与请求预检功能。

## Artifacts and Notes / Interfaces and Dependencies

证据将写 `docs/v4/evidence/P3/2026-10-21-quiet-stream-cancel.md`。新增关闭辅助方法与 close_on_cancel 的可选活动响应回调，既有调用仍兼容；无依赖/配置/数据库变更。

## 修订记录

- 2026-10-21 07:44 创建，记录真实失败位置、最小修复范围和 Linux 未验证边界。
- 2026-10-21 07:47 记录候选实现、本机59模型+3真实PG目标通过及静态检查；首次测试包相对导入收集错误已修为共享fixture绝对导入，未放宽测试断言。
