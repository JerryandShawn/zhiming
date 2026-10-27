# P4联合切片回执：真实timer、事件提示与HTTP

- 分支 / 起始提交：`v4/p3-wire-p4-20261021 @ 8c35aff322c4c4860eeb2ae5b67e01169589815b`，tree`a92c9843`；收口时已提交HEAD为`a1270174e6f64cfe1abe915a09836647c1da3484`。本片仅3个新测试/helper及计划/证据，待root审查提交，Draft PR14未合并。
- ExecPlan：`docs/v4/execplans/P4_stream_hints_joint_20261021.md`。
- 时间：2026-10-21 10:51，北京时间UTC+08。**最新明确目标3/3通过，但历史跨进程超时根因未实证；不能宣联合稳定、完整P4验收或部署许可。**

## 完成了什么

只在可信装配同时启用`AgentRuntime(streaming_candidate=True)`与`create_app(event_hints=True)`。真实Uvicorn socket、原loopback quiet HTTP fixture、真实OpenAICompat、PG/Journal/RequestLedger/dispatcher/hub/LISTEN/SSE均参与，没有ASGI TestClient或伪造PG结果。生产源码、游标代理文件、Schema、模块源与旧断言0改。

同进程门使用实际assembly.signals.controls。真实HTTP建life线程/发消息、dispatcher执行，SSE先进入等待才允许本地provider开始HTTP；不足40字片段在provider仍静默、尾gate未释放时，已存在真实PG并通过通知到SSE，seq/body精确匹配。随后释放尾得到core4 final，只有1个物理loopback请求。

跨进程门的父app明确agent=None，仅提供已鉴权reader/事件提示；run先由已装agent服务真实submit。新Python进程用固定源执行真实Runtime，原model/step/请求账本/stream generation均由实际服务生成。父HTTP在首delta后断开，带真实Last-Event-ID重连，再释放provider尾；前后seq与真实PG全集一致、无重复，child内存断言只允许成功core4和1次物理请求。此门没有验证父dispatcher执行，不能混报。

取消门在首delta已经到SSE、provider仍静默时，真实POST `/api/runs/{id}/cancel`，实际PG cancelled与SSE终止合计<2秒。quiet port finally结束，本次actor.done/线程退出，pool所有借用归还、requests_waiting=0，无final。释放旧provider尾后200ms内事件全集不变、请求数仍1；应用退出后listener/订阅归零。这里只核本次对象，不停共享PG、不结束他人进程。

父客户端显式trust_env=False，并在测试中强制所有同步httpx客户端禁系统代理；只允许http://127.0.0.1。child白名单OS环境、无PG/HTTP代理/凭据继承，`-I -B -X pycache_prefix=<os.devnull>`；stdin严格核loopback test库、随机p2_test schema、固定alice/run与provider URL后才连接，真实PG版本15。DSN仅进匿名stdin管道，不进argv、文件或stdout；child安全输出仅成功/计数或受控phase/异常类型/源文件帧，未输出原异常消息/正文/凭据。真实模型、外部供应商、服务器、飞书0。

## 实际验证与首红

统一使用root安全runner、P2 Python/本机随机schema，清供应商/追踪，TZ=Asia/Tokyo；记录显式+08。只一个窄进程串行，不运行目录全量。

| 本机时段 +08 | 目标 / 实际结果 | 原始目录 |
|---|---|---|
| 10:46:08.641619→10:46:11.924959 | 同进程单例1 passed/2.27s | `private/safe-narrow-be172b0f46c942e1a8db05de67be7cdc` |
| 10:46:34.050567→10:46:45.217446 | 全3门：1 passed、2 failed/10.19s | `private/safe-narrow-b860e93ed23f4a64aead2b4cf211137c` |
| 10:48:35.884059→10:48:46.213777 | 跨进程/取消：1 passed、1 failed/9.23s | `private/safe-narrow-30ec5a715877435b85f0361441a8a195` |
| 10:49:45.715646→10:49:51.411714 | 跨进程单例1 passed/4.66s | `private/safe-narrow-3b8dbfa2be464911a95152b7a65c6bf0` |
| 10:50:34.047357→10:50:42.215494 | 最新全3门：3 passed/7.22s，0fail/error/skip | `private/safe-narrow-cfe5a901fe764e0a88e0a653dbf4f1f0` |

明确命令（首个单例/两目标按上表以`::<测试名>`选择，最终如下）：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 tests/v4/streaming_integration/test_stream_hints_joint_http_pg.py

首红b860包含跨进程首delta读超时，以及取消PG已cancelled而终态SSE读超时。当时全部用例都把Subscription.wait的回退等待人为设为5秒。root确认：delta门保留5秒以证明mj_run通知；取消门用受信默认150ms验证<2秒，原计划并未要求人为5秒fallback下也<2。仅测试配置恢复默认，2秒/状态/资源/无迟到断言未放宽，生产0改。实际取消状态转换尚未主动发事件channel mj_run、依赖默认PG回读，是保留的通知差额，不能称已修复。

跨进程第二次30ec在quiet.started断言通过后仍首delta读超时。之后只新增分离冷启动与提交读取的等待、安全phase/源码帧诊断，单例及完整3门通过。**没有证据可把两次旧超时归因冷启动或认定已修复。** 未xfail/skip或删除首红，后续绿不关闭历史间歇。root将在只读审查后决定是否将该候选纳入后续固定回归；11点候选可以不含本片。

## 失败时点：已有证据与未采集项

以下是原始日志和当时实际执行到的断言能证明的最细粒度；没有录下的时间点明确缺失，不倒推或补造。

| 观测 | 首次跨进程超时 b860 | 第二次跨进程超时 30ec |
|---|---|---|
| 整个pytest起止 | 10:46:34.050567→10:46:45.217446 | 10:48:35.884059→10:48:46.213777 |
| 父HTTP/SSE注册 | HTTP200且entered.wait(1)断言已过；订阅/首wait已发生，精确时刻未采集 | 同左，精确时刻未采集 |
| child开始/安全phase | Popen已启动；未保留阶段/安全stdout原件，不能判导入或execute状态 | Popen已启动；未保留安全stdout阶段，不能判execute后结果 |
| quiet.started | 超时前没有执行该断言，是否已发生未采集 | started.wait(5)断言已过；说明首个loopback HTTP片段已flush，精确时刻未采集 |
| 首delta的PG落库 | 没有失败时PG快照或PG时间原件，是否已落库未采集 | 没有失败时PG快照或PG时间原件，是否已落库未采集 |
| 父SSE首delta | through(...,delta=True)发生ReadTimeout；未收到该预期边界，不能据此推出PG没有row | 同左 |
| child stdout/stderr | 旧cleanup读取/关闭pipe但未将返回值持久保存；JUnit没有阶段输出。没有可恢复的安全诊断 | 同左 |

后续3b8/cfe源已加入安全诊断：失败时只报告child阶段/异常类型/源码文件函数行，以及父PG状态/无正文stream计数。两次后续通过并未触发诊断分支，因此也没有补出旧失败的阶段。最新成功child stdout在内存断言为`{"succeeded":true,"physical_requests":1}`，未独立保存stdout原始字节；不能伪造原件SHA。最终各事件精确单调时间也未额外采集，当前证据只证明测试中先后顺序及<2秒断言，不给虚构的毫秒数。

## 关键新文件与安全产物摘要

| 文件 | bytes | SHA256 |
|---|---:|---|
| tests/v4/streaming_integration/test_stream_hints_joint_http_pg.py | 9030 | d61f850d19365c3356649935cb3e31e3c7403db21a36356c370d42364c1d6f28 |
| tests/v4/streaming_integration/stream_joint_http_support.py | 5661 | 44d698d8d4cdc8d6bf9341305fa2b38d94e6d7cd5cf91c0d4c5175938fa4d472 |
| tests/v4/streaming_integration/stream_joint_process.py | 3423 | ba5584271b63ce3e3e6b07edc2c293761df427fddbafd21ce8be7c695fc19809 |
| b860 pytest.xml | 7387 | 455d17ca53fb403d4b4a9d87a7296b465f5880e9d5c3c0745d7ea5cd161d0f71 |
| b860 pytest.log | 6961 | 603b71d08d059f6d72cde515fd703e1d3a0141bc105bee41e9eadfc9f9dc8a9d |
| b860 metadata.json | 457 | 27762bf02e2197063dcbb0491f3babbf55cc5e5969d88aeb2ad272a96d394ca1 |
| 30ec pytest.xml | 3942 | 1de43843eedc87a78f447567889946f52d499238f1b34a62303fb20c30e91608 |
| 30ec pytest.log | 3613 | 8ed57aacd7329ce12ef06cb450ee331853b87fa10834f8b6821845c32e334ee1 |
| 30ec metadata.json | 667 | dfdb2e98bc8a110fb7634fbc681b7f720cab37162e0c86a71a08577b0c98983c |
| 后续跨进程 pytest.xml | 497 | 75787b4c22261b4b526d698402a835aa353a58072cc196683fe17abe74f6fa73 |
| 后续跨进程 pytest.log | 100 | e1372ffc2b5f64ee88082a7db27545cb64b8b7594d8ccb2d8e2fb98bcb478daa |
| 后续跨进程 metadata.json | 523 | ebfc07a65c582447008fdd37b1f9cd2a64f3136eabf3708c35937eb7a1c63511 |
| 最新3 pytest.xml | 1015 | a7237c3905eca5faf9a9a95f6767d1e59019a55cd7889ef77c8a4d0c949da99c |
| 最新3 pytest.log | 100 | 1c936aaae1b36e37c6b363491bb72005a1974d2ef02a89ffd6be003deb1a1a34 |
| 最新3 metadata.json | 457 | 8a6c944a97651d410aca7474e3e565a137097face24413fd7022ccabbc1412cb |

Ruff E/F/I/B/UP/SIM、120列format、AST/400行/函数60行与diff检查通过。三个文件分别180/157/93行，最大函数60行。全程只有3个新测试/helper，不修改生产或其他代理文件；没有新依赖、迁移、API或Schema。

## 未验证、回滚与待决

本片仅新增测试，生产开关仍默认关，无数据库迁移或部署回滚动作。跨进程旧首delta超时根因未实证，取消终态主动mj_run通知未实现；最新3/3不解除这些差额。完整P4/X08全部边界、24h清理、旧DOM、P3 X03/encoder与B1 No-Go仍保留。10:50已释放窄槽，不再pytest，11点回归是否包含本片由root审查决定。
