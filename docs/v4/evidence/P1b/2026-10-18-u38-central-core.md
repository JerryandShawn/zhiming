# P1b U38 中央守卫核心子范围回执（阶段未完成）

- 分支 / 测试时基底：`v4/p1b-k3-hardening @ 43a119b69241c1d4b4def8877b6526bd826514c3`；本次源码未提交。PR #9尚未包含本次未提交文件，发布/CI由root负责。
- ExecPlan：[P1b_k3_hardening.md](../../execplans/P1b_k3_hardening.md)。日期：2026-10-18 23:02 +08:00。
- 最终源码身份：[结构化校验清单](u38-central-core-validation-2026-10-18.json)，包含13个执行/测试/迁移文件的SHA256、Git blob SHA1、逐文件静态边界及0001–0007不变证明。没有密钥、真实用户资料或对话正文。

## 完成了什么

- [x] 显式中央账号身份：构造时必须提供中央DSN、schema、account_id、固定ledger UUID；核验实际DB/地址/端口/schema的位置摘要。运行构造不自动建账号，复制账号行到别的业务schema不能通过核验；不同业务run共享同一账号账本，确为不同账号才独立。
- [x] 真实PG跨进程在途≤2：每次准入持有独立session advisory slot，连接关闭释放；一个槽预留给交互，critic/background/eval/probe只使用另一个。交互最多等10秒，后台可排队/取消。两个独立spawn进程持槽时，第三个超时且MockTransport为0POST。
- [x] 实际发送前持久reserve与滚动5小时≤80：账号行短事务串行核预算，发送期间不持有SQL事务。全部尝试及未知结果保守占用窗口；业务run变化不重置。默认60/20/20份额（48/16/16），交互可借余额，critic和后台不可借；eval/probe并入后台池，另受eval上限约束。目标、评审、探针分别发POST就各占一次。
- [x] 持久全停：5h/周/月/quota、并发风控、Access terminated均跨连接/进程保留；风险更高停止不会被后来的较弱错误降级。80窗口命中也持久停止；到期仅显示最早人工检查时间，不自动恢复。并发风控不降到1继续。已观察到终止错误时，即使时钟回拨仍记录结果/stop，后续准入继续拒回拨。
- [x] 显式批次授权：每批1–10个不同场景、当前授权ID与场景集合一致、到期拒绝、完成后持久20分钟间隔。授权永久一用，重启不会开始新批；clear、recovery、batch共用append-only授权ID账本，旧clear重放不清新stop、不让新批过期，恢复ID不跨batch复用。
- [x] 未知结果人工收口：进程强杀后session槽释放，已reserve不退款、不重发。`close_abandoned_batch`必须持有两个空闲槽并带独立人工恢复ID，才把旧pending记为unknown、结束旧批；不清全局stop，不启动下一批，20分钟间隔保留。两个槽活跃时拒绝。
- [x] 新迁移0008与降权：7→8保留既有数据且重复初始化幂等；新表运行角色可执行所需DML，但不能建账号、删用量/授权、改授权历史、改迁移账本或建表。原1–7不改；旧schema7发行版拒绝schema8的负例保留。
- [ ] 真实HTTP入口/旧ConfiguredModel/Registry/内部重试/评审/探针/runner全部接线；本次只交可验证核心，不声称入口已受到中央保护。
- [ ] 中央部署拓扑、可信配置装载、用户在线逐批启动与通知入口、完整U39、真实等价和k3-256k切换；均未完成。

## 评测分数与验证

- 最终本地主要回归：**736 passed，74.13秒，0skip，exit 0**。其中新增6个guard模块79项（48项真实隔离PG、31项纯契约）均包含在本次实际运行内；不是只做schema校验。
- 实测模型：**0次真实请求**（含探针）；没有分数。不访问stage/生产/服务器、不SSH、不发送飞书、不启停共享PG。
- 本子范围未跑scripted80/48、整库Core/v4、coverage或CI；不得借用前轮成绩冒充重新验收。

测试cwd固定为`C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b`，解释器固定为P2 Core。测试进程删除所有名字匹配`API_KEY|AUTH_TOKEN`的环境项，并将`LANGSMITH_TRACING`与`LANGCHAIN_TRACING_V2`设为`false`；没有持久环境变更。测试命令：

```powershell
$env:CORE_TEST_DSN='postgresql://core_test@127.0.0.1:55480/core_test_main'
& 'C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe' -m pytest tests/v4/models tests/v4/test_p2_foundation.py -q --tb=short -o faulthandler_timeout=60
```

本地完整最终输出：`C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/night/u38/models-frozen.log`。新增测试通过现有`p2_repo`连接真实PG，每case随机独立schema；进程共享该case的中央schema。所有新增HTTP通过MockTransport；不以Mock数据库替代账本。只有测试子进程被强杀，不是PG进程。

最终静态检查使用主树Core中的Ruff，显式`--select E,F,I,B,UP,SIM --line-length 120`，并执行同文件`ruff format --check --line-length 120`。4个新核心模块、permissions、6个新测试和foundation共12个Python文件全部通过；新增文件≤400行、全部函数≤60行、单行≤120字符、UTF8无BOM/LF及`git diff --check`通过。外部复核脚本：`C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/night/u38/validate_u38_static.py`；脚本不装依赖、不调用模型、不改执行源。

过程说明：初次Windows强杀用例的清理又访问被杀进程的Event，会卡住测试退出；未把该次当全绿。只结束本次pytest父/解释器，改为不触碰已终止进程的同步对象。后续6项进程测试10.71秒通过；42项/33.45秒与733项/70.15秒为中间源码结果，最终以736项为准。两份遗留schema严格按本次合成case的attempt集合和初版0008校验和识别清理，未碰其他schema。

## 关键文件与接口

- `mingjing_core/models/quota_guard.py`：`QuotaGuard(central_dsn, central_schema, account_id, ledger_identity, clock, policy)`；`acquire(role,lane,attempt_id,provider,model,...)`返回上下文内`Attempt.result(kind,usage)`；批次begin/finish、record_stop/clear_stop、显式unknown恢复、status/critic_allowed/background_allowed。
- `quota_store.py`：短事务预算/身份/用量/stop/人工操作ID；`quota_batches.py`：一用授权与批次；`quota_types.py`：默认策略、受限标识与安全领域错误。
- `repositories/migrations/0008_model_usage.sql`：账号、用量、批次、append-only授权四表；`repositories/permissions.py`：按表收窄运行角色，不改变旧返回接口。
- `tests/v4/models/test_quota_guard_{pg,batches_pg,process_pg,recovery_pg,migration_pg,contract}.py`；`tests/v4/test_p2_foundation.py`仅两处当前版本预期7→8，其数据保留/幂等/拒未知历史等保护不变。

后续接线必须从可信配置确定账号、角色和lane，每次物理POST都用唯一attempt_id；在httpx实际包体预检通过后reserve，再执行已有meter/count与同一个Request的send。内部重试必须另占attempt，流式响应须在完整读取/关闭后才释放上下文。单次generate外包一层不足以证明所有POST计费，现有eval MemberBudget也不能替代本中央账本。

## 数据库迁移与回滚

仅新增0008，旧1–7的规范化checksum与Git对象不变。账号provision是迁移/管理员动作，运行构造失败关闭；运行角色不能自行开新账号绕过额度。测试中的两处版本预期更新经root明确同意并记录Decision Log。

无降级SQL，不删账本。schema8不能直接跑只认识schema7的旧发行版；应用回滚需选兼容schema8的代码。若必须恢复旧数据库，要另获授权、先停止所有调用并保留/核并新增用量和stop；直接回滚旧账本快照会丢失已发送计费状态，本次未实现或演练该部署流程。迁移角色/运行角色应分别配置，session advisory锁需要直连或保留session语义的连接方式；事务池代理未验证。

## 偏离设计及理由

夜间用户队列8与root独占授权覆盖旧模块分工，在P1b实现核心；没有同名并发guard文件。核心以显式类型策略起步，不虚构不存在的runtime.yaml装载器。eval/probe采用后台20%池的保守划分，默认每窗口后台/目标仅16次、critic另16次，不承诺一次窗口可跑满80个评测POST；交互优先与所有调用总≤80同时有效，正式入口配置应确认这一路由。

## 未验证 / 已知风险

中央库位置摘要与固定UUID能拒错误/复制schema，但不能证明操作方把所有服务都指向同一真实账号账本；跨业务DB的实际中央DSN/schema/account映射、凭据分权和部署拓扑仍待交付。角色/lane当前是可信调用接口，尚无入口配置防用户输入伪装角色。人工ID提供幂等和一用，不能自行证明真人在线或聊天授权；启动入口仍必须实施该校验。

既有旧ConfiguredModel/v3、全部streaming/Registry/retry/eval/probe接线未完成；尚不能声称当前线上/旧路径已受中央限额保护。提供者计费的真实语义、断网/DB故障/代理拓扑、完整U39、实际k3-256k能力和等价子集均未实测。reserved是保守预算占用，不是确认供应商收到了请求；unknown token保持null。P3、模型配置、web及服务器状态均未改变。

## 需要用户或大脑决定的问题

正式部署时确定唯一中央账本的DSN/schema/account身份与管理员/运行凭据分工；正式评测/探针接线确认后台20%池的预算归属。此处不需要夜间等待答案，默认继续保守核心、0真实调用。k3-256k真实等价及探针须等用户在本聊天明确开始，当前不得切换。

## 建议后续

root核对本子范围后单独提交推送；再完成可信runtime配置与每个实际POST入口接线、人工批次启动及通知门，随后推进U39。没有真实授权只做离线工作；P1b整阶段、CI与部署均不由本回执宣布完成。
