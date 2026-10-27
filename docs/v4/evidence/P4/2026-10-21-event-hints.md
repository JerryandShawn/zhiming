# P4 M3首片：真实LISTEN到HTTP消费者的有界提示

记录时刻：2026-10-21 10:25:11 +08:00（工具UTC 02:25:11换算，北京时间）；本机TZ=Asia/Tokyo。目录为`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，独立P4 Draft候选；root统一提交推送，本记录不代表合并、部署或P4验收。

## 最终结果

一个窄pytest进程串行运行四个独占新目标：**28 passed/8.72s，0failed/skip/xfail/warning**。18条纯边界、2条真实PG监听、8条真实Uvicorn/socket HTTP+PG；原输出在`private/p4-event-hints-20261021/final-target.log`。使用显式本机隔离PG15（55480、每条测试独立随机schema）、清供应商凭据、关闭追踪；最终HTTP客户端均`trust_env=False`，子进程仅真实本机PG、没有HTTP。未访问stage/生产，没有真实模型请求/飞书发送、没有Docker/WSL尝试。

    python -m pytest tests/v4/streaming_integration/test_event_hub.py tests/v4/streaming_integration/test_event_listener_pg.py tests/v4/streaming_integration/test_event_http_pg.py tests/v4/streaming_integration/test_event_http_lifecycle_pg.py -q --tb=short

Ruff E,F,I,B,UP,SIM（line-length=120）及默认ruff format检查新增/重构10个Python文件通过，git diff --check通过。5个生产文件里`web.py`仅最小接线，不整体重排其旧格式。新增文件≤400、最大函数≤60；最终精确raw-byte manifest另存私有目录供root重算。

## 可观察证据

| 目标 | 实际行为与断言 |
| --- | --- |
| `test_event_hub.py`（18） | 4线程发布3000条+3000未知run，暂停loop时仅1个app pump；2000次订阅/退订仍1待调度callback；每订阅queue高水位1；全局256、每run32、每app128、app scope16硬上限及幂等释放；伪极高seq消费后更低真实提示仍可唤醒；未知通知不建cache。 |
| `test_event_listener_pg.py`（2） | 同进程两scope实际PG中仅一条专用application_name连接；外层事务提交前无提示、rollback无提示；commit才交付；真实终止自身监听连接后重连为不同pid，关闭后数量0。 |
| `test_real_http_is_woken_by_fresh_process_commit_not_the_fallback_poll` | socket HTTP已进入空闲wait后，先接收不存在行的伪极高seq，reader回查不跳cursor；独立Python进程实际运行leased RuntimeEvents，在同一PG事务写started+text_delta。只把测试等待兜底延长至5秒，HTTP读超时为2秒，两个真实帧仍到达，证明实际LISTEN→Hub→reader→HTTP，而非150ms轮询冒充。关闭HTTP后订阅0、run仍running且无cancel标记。 |
| `test_real_http_replays_over_one_thousand_rows_and_reconnects_at_actual_cursor` | 真实写1004行后实际fail_run，HTTP取得连续seq1–1005（最后真实RUN_FAILED），跨4个256行分页无漏；Last-Event-ID=999只重放1000–1005。 |
| `test_real_http_auth_cursor_and_untrusted_hint_cannot_disclose_other_owner_or_jump_rows` | bob鉴权不能读alice run，游标超max在header前422，均不留订阅；极高伪通知不授权或跳过实际seq；响应没有lease_token。 |
| `test_candidate_default_has_zero_listener_and_http_cannot_enable_it` | 未传可信开关时连接0；HTTP query event_hints=true不能开启；非bool可信参数明确拒绝。 |
| `test_http_reads_real_pg_while_its_actual_terminated_listener_waits_to_reconnect` | 真实pg_terminate_backend只终止本测试自己的监听pid；在测试受控暂停重连期间通知计数0，HTTP仍经真实PG轮询得到started；放行后仅一条新监听、断线订阅0。 |
| `test_two_actual_app_event_loops_share_one_connection_and_release_independently` | 两个真实Uvicorn app与独立loop共一条LISTEN，两HTTP订阅收到相同真实帧；一个app关闭后另一仍持单连接，最后关闭0。 |
| `test_real_http_uses_actual_terminal_and_never_reconstructs_cleared_originals`（2） | 真实来源撤销清原事件正文后仅返回seq3 SOURCE_REVOKED，无旧片段复活；真实DispatcherCancellation终态RUN_CANCELLED；迟到写端均拒绝，HTTP没有迟到结果。 |

提示仅包含run_id/seq，owner字段仅是订阅scope标识，**hint不作owner授权或per-owner限额**。每次事件正文与游标都由原RunEventReader鉴权/人物/线程和真实PG行决定；提示高水位不会写入cursor。每app最多一个pending loop callback，subscriber churn不会留下大量旧callback；同一run的提示可促多个owner scope回读，真正授权仍在PG读取端。

## 初始失败与修复记录

首次两个新目标的collection因无包目录相对导入失败1条，测试未执行；已改为仓库现有tests命名空间绝对导入。首次HTTP四条原请求均返回502：**4 failed/10.55s**，原工具输出chunk `88069e` 保留；请求URL为`http://127.0.0.1:<临时端口>/api/...`，测试未注入代理。

之后只读诊断（没有再次发送代理请求）确认：代理环境变量键列表为空，但Windows用户代理注册表存在http/https/ftp配置；httpx默认为这些127.0.0.1 URL选HTTPProxy，`trust_env=False`选择ConnectionPool。没有输出任何代理地址、用户名、口令或真实正文。最终测试显式禁用环境/系统代理，保护直连目标；不能把最初误路由4次声称为“全程仅loopback直连”。此前4 passed/6.10s与28 passed/8.73s为中间结果，最终独立重跑以上28项8.72s；没有改旧断言或将错误转xfail。

## 关闭、回退与未验收边界

默认`create_app(..., event_hints=False)`，可信bool显式开启才安装。不同数据库配置在同process明确拒绝，不开第二条连接；最后app卸载先关闭旧listener再撤全局broker，关闭失败留closing门。thread_events生成器和Response层finally双保险退订；通知丢失/重连时仍原150ms PG补读，不取消run、不重发业务效果。专用连接只LISTEN mj_run，不接管dispatcher取消/队列通道。3秒join是app卸载时的有界线程检查，不是2秒取消证明，也不是所有网络黑洞下连接关闭的硬期限。

精确seq存在/清理墓碑、after查询别名保持未完成；原validate_cursor仅拒大于max。旧DOM对命名事件的逐字消费、M2a定时flush/完整Runtime联合链、保留清理与完整X08、真实供应商首字/背压内存/全部P4验收均未由此28项证明。测试跨进程写端是实际M1 RuntimeEvents，不偷换成“完整模型流已完成”；M2a源与结果独立归其作者，本片未改。没有修改Schema/core4/迁移/锁依赖。
