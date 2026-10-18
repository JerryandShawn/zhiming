# P1b 离线首切片验证（2026-10-18，阶段未完成）

已完成 U37 错误分类/动作及 transport、Registry、typed eval 兼容的离线首切片，并完成禁止关闭会员 K3 思考的配置闸门。U38中央守卫、U39完整推理回传等后续工作尚未完成；真实模型请求0，不能据此切换线上模型或宣布P1b验收完成。

## 源码与发布边界

分支 `v4/p1b-k3-hardening`，基底 `v4/main@b9a89b6f84f7bebb640de080548010859aae630c`。本地代码提交 `2cf6b1f1edefac46e2b5d035484713326eacf7d0`；root提供的不可变远端代码对象 `be8119e475034306681b6d168ab49073b2a23b76`，等价代码tree `ff652a9d1e4a8b64cd83e364aebf10be1234cb47`。代码与本证据由root统一发布至草稿PR #9；最终精确头CI由发布后核验，不能借用旧计划头结果。本地通过不代替CI绿门，不合并P1b。

## 实际检查与源码时点

| 检查 | 实际结果 | 原始日志（留task，不复制正文） |
| --- | --- | --- |
| 旧Core全集 | 553/553，638.777s；root观察退出0，日志553/OK | `p1b-core-full.log` |
| 全部models与coverage | 511/511，75.04s；903/944语句，95.6568%，显示96%；95%门通过 | `p1b-model-coverage-final.log` |
| 全部v4 | 918/918，153.58s，零skip；1项上游anyio弃用告警 | `p1b-v4-full.log` |
| 原脚本及框架自检 | 80/80、自检48/48，10.72s；真实POST0 | `p1b-scripted.log` |
| transport与PG边界 | 92/92，2.72s | `p1b-boundary-pg-final.log` |
| 静态 | root已完成Ruff、formatter与AST行数/函数/类型检查；文档收尾不重复运行测试 | 原检查记录 |

日志均在task `work/daytime/`。完整字节长度/SHA256与结构化结果见 [offline-validation-2026-10-18.json](offline-validation-2026-10-18.json)。测试限本机PG15、loopback55480/core_test_main可丢弃schema，Core/Charts解释器分离，模型凭据清空、追踪关闭。外部模型仅HTTP替身，不绕过真实PG/业务服务。

**源码时点不能合并描述**：Core553在同一生产切片的回归过程中运行，早于最终的“非会员HTTP402保留旧BadRequest且不重试”窄改。最终全models511与全v4918重新覆盖该修改；没有宣称Core/script/boundary等日志都来自最终代码提交的同一瞬间。最后代码差异与测试反例已经核对，日志原字节保留，不事后重贴源码身份。

可复验入口如下，实际成绩以上表及日志摘要为准：

    python -m unittest discover -s tests -p 'test_core*.py'
    python -m coverage run --source=mingjing_core.models -m pytest tests/v4/models -q
    python -m coverage report --fail-under=95
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test

## 错误 → 类型 → 已验证动作

下表是离线分类/当前调用链动作，**不代表PG账号级持久全停或通知已接线**。所有受控错误保留旧ModelUnavailable继承兼容；PermissionError与PermissionDenied为同一类兼容别名。

| 输入/边界 | 类型或kind | 已验证动作 |
| --- | --- | --- |
| 403 + 严格嵌套permission_error + 5h/week/month额度 | ModelQuotaExhausted；quota_5h/quota_weekly/quota_monthly | 当前链1次、不重试、不切同会员；输出global_stop/persistent_stop策略，持久执行待U38 |
| 会员并发/Access terminated信号 | ModelConcurrencyLimited / permission_error(kind=access_terminated) | 当前链立即停止、不fallback；人工全停/通知策略已声明，跨进程执行未实现 |
| 其他403 | ModelPermissionError | 不重试，不用回显文字猜额度 |
| 会员402 | ModelMembershipUnverified | 同provider最多2次；60s重试一次，取消/deadline可提前阻止 |
| 非会员HTTP402 | ModelBadRequest | 保留旧契约，不重试；反例与最终models/v4覆盖 |
| 会员429/引擎过载 | ModelRateLimited；rate_limited/engine_overloaded | 同provider最多4次，1/3/9s加抖动；不再一律归额度；后续仅显式非会员候选可fallback |
| 非会员严格insufficient_quota | ModelQuotaExhausted + provider-quota动作 | 1次，不制造会员全停；仅显式非会员fallback |
| 400缺reasoning_content | ModelBadRequest(kind=reasoning_missing) | 不重试，保留代码缺陷分类 |
| 400体积/token/安全拒绝/其他 | payload_too_large / token_limit / ModelContentFiltered / bad_request | 不重试；本地体积预检与上层压缩仍待后续 |
| 5xx/连接失败 | ModelUnavailable | 同provider最多4次，统一退避，受总deadline/取消限制 |
| 流式未知错误 | ModelUnavailable，NEVER动作 | 不凭正文quota/429猜状态，不重试；HTTP/SSE共用纯分类器 |
| 已有text/reasoning/tool_call后的失败 | 原受控类型 | 不重播、不fallback；quota统计保留 |

78项HTTP/SSE合成矩阵经过纯分类及真实adapter/MockTransport边界。未录制的供应商文案标为格式推定，不称真实供应商验证。配置校验同时覆盖静态model、effective env model、缺key前拒绝、resolve后数据/环境变化和直接adapter构造；None/未指定走服务端默认，不把旧budget或未知effort误判为关闭。

自定义factory原可产生4×4=16个HTTP attempt；Registry现在每attempt暂时强制StreamingHTTP的内部max_retries=0，并在成功/失败/取消finally恢复。新增回归证明失败恰4次、一次失败后成功恰2次、取消恰1次。fallback限制为显式非会员，当前默认会员链不借同账号其他模型绕过。

typed eval stop直接识别受控kind：5h/week/month/concurrency/access保持各自stop_reason，429/402穷尽重试后为provider_http_error，不重新归为quota。额外纯内存7类停止检查中，两次调用仅触发底层provider一次；这是本进程控制信号检查，不是U38跨进程持久化证据。

## 旧测试变更与夹具来源

原测试保护过“一律把会员429或正文quota当额度停”的旧策略；P1b §A明确替换该行为，因此只更新这些已被新规范取代的断言。真实403额度恰1POST、隐私、取消、总deadline、可见输出不重播、业务charge/repair不重开继续保留。PG shim旧quota用429的夹具改为403公开额度句=1物理POST、429 rate=4物理POST，两者仍只有1次旧v3业务charge。初跑430通过/1失败及未最终通过的覆盖结果不计为绿，修后完整重跑。

正式合成夹具为 [`tools/eval/fixtures/u37_error_matrix.json`](../../../../tools/eval/fixtures/u37_error_matrix.json)，已跟踪，78项，SHA256 `853719fc0b9893f1b69704415f696778b5949f5fe9cf377dc012c0858ddb7156`。已从被gitignore保护的 `tests/v4/models/fixtures/` 候选位置移至AGENTS规定目录，两处测试加载路径同步更新，没有强制加入ignored夹具。

矩阵内的 `source_design_sha256=92396c24196e22de4dc5694ac57bbf457f63aac35c147ef5735aa41f74569547` 已核实指向task `p1b-error-matrix.json` 的**84项派生离线设计矩阵前身**，不指大脑原件；6项transport/local执行设计另由实际边界测试或后续工作承担。当前P1b原提示词的独立SHA为 `e403a07903217d537b69e2482806c28619328abe5c28a30747b16fc4ccb8da8b`，两者不能混称。

## 剩余范围与运行决定

P1b阶段仍未完成：U38中央PG账本、reservation、专用连接槽位、持久全停、迁移0008和全部入口接线未实现；U39完整推理/签名回传及effort锁定未完成。采样移除、tool_choice限制、1.8MB体积预检、人工批次代码闸门、新256k兼容E1来源、真实探针与实际模型切换均未完成。config/models.yaml仍未据真实探针切换，不把禁关思考子项当完整U39。

D1继续全部用会员端点；未来守卫必须项目全局在途≤2，concurrency_limited/Access terminated持久全停、通知并等用户。所有业务库、评审、E1及probe应显式共用一个ledger DSN/schema/account namespace，不能各业务DB/schema单独建“全局”锁。quota_guard.py核心与单测归独立模块线，主线负责迁移及真实接线；本切片没有创建第二套假guard。

真实E1/E2只在用户在线且本聊天明确开始该批后执行，每批≤10、批间20分钟、目标/评审/探针/重试共用≤80实际POST/滚动5小时，夜间零调用；旧自动续一次规则不能替代用户授权。D2主/评审目标k3-256k，≤20次等价性子集和探针同样等明确开始；当前未切换。D4提醒默认关、无紧急联系人；D5 E2仅2025子集。P3负责上下文守卫，P1b不改P10/web或P8/charts/skills/knowledge。本轮没有stage、生产、真实飞书操作。
