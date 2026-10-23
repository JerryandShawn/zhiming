# P1b v3 默认路由及物理请求规范第四切片

记录：2026-10-21 00:07 +08:00（北京时间）。仅本机隔离PG15与HTTP替身；真实模型、服务器、飞书均0。root统一提交，PR9草稿。

## 改变与影响

`ConfiguredModel` 不再凭旧用户环境 KIMI_MODEL=k3 降低会员默认：未显式给模型时，默认Code endpoint与k3-256k。显式历史k3构造保持可见身份，未改冻结E1/v2.1产物；实际批次依旧必须用户在线逐批人工授权和中央PG核验。非会员显式服务/模型的旧请求与解析保留。

所有旧会员实际请求先过 `legacy_request_policy.member_body`：调用角色可信绑定，K3思考/effort配置检查，旧1024 thinking预算及temperature/top_p移除，使用文档默认auto/high而不猜effort wire；单工具选any，named/none、显式关思考或低effort发送前拒绝。最终httpx request再经原1.8MB检查、中央permit、meter与send，用量/终止持久停止仍同一中央账本。显式历史k3不被改名256；原始body不被就地修改。

该旧结构化接口只允许一条全新user内容（text/image）与一次submit，不接受assistant、tool、tool_result或其他推理历史。此类输入返回 `LEGACY_CONVERSATION_UNSUPPORTED` 且0POST/0reserve。影响：需要保留助手推理、签名和工具回传的连续多轮调用必须经规范ModelPort与RuntimeRouter迁移；拒绝旧输入是失败关闭，不是宣称多轮兼容完成。旧接口原本每generate均构造单条新user，不把上轮私有推理写回此路径。

## 已验证

新策略、旧中央PG、会员错误与旧模型诊断四目标：47 passed、19 subtests passed /2.97s，零skip；保留旧imported test_dsn返回str的pytest警告。真实PG同时核sanitized wire只记录一次成功，而assistant历史、关思考、低effort、none均0额外POST/0额外reserve。旧显式k3成功例仍记录k3/critic份额，wire不再包含thinking/temperature。

北京时间00:06窗口启动models+五份eval+旧模型诊断宽回归，一个进程，结束后追加最终实际结果。没有安装依赖、没有访问实际供应商，不把auto/high文档默认称实测。

## 边界

新文件不足400行、函数≤60，Ruff指定规则与120列将随冻结复核；老adapter只改三行必要路由，保留既有格式和业务解析。没有新迁移，也没有部署或合并。规范多轮Runtime、真实模型等价/高低effort与中央账本部署仍需各自验收。

## 最终复核（2026-10-21 00:09 +08:00）

00:06窗口开始的宽回归完成：**1030 passed、19 subtests passed /101.24s，0skip**。范围为整个tests/v4/models、五份eval(framework/quota/quota_pg/critic_contract/resume_comparison)、旧Core模型诊断。仅保留一条既有imported test_dsn返回str警告。该结果覆盖第三片旧subset fixture修复及本片最终新增真实PG关思考/低effort/none零POST负例；非整库Core、非整库v4、非CI。

Ruff E/F/I/B/UP/SIM、120列通过；新增两文件<400行、函数≤60。旧adapter仅必要行改动，未整文件格式化。实际运行解释器为既有P2 Core，静态工具为既有主树Ruff。

## 最新供应商HTTP入口盘点（覆盖前切片历史表）

| 路径 | 准入与剩余边界 |
| --- | --- |
| OpenAICompat/AnthropicMessages → StreamingHTTP._request | 每物理POST和重试中央PG；规范推理/签名/角色/high/size策略保留；SSE释放/取消/全停已测 |
| ConfiguredModel → quota_legacy.post_legacy | 同一中央PG，当前K3单新user规范wire；连续工具历史明确失败关闭，需ModelPort迁移 |
| Registry/PortBackedModel/runtime角色 | 底层共用StreamingHTTP；角色可信构造，实际运行参数不能改变；默认锁256 |
| eval engine/v21/runner/subset/ModelJudge/EvidenceModel | engine场景scope+包装lane+构造角色接线；已有TTY收据才可实际evalPOST；旧冻结k3身份不冒充新256报告 |
| tools/probe_models.py | 当前收据指定最多10场景，probe lane每POST中央核批；无收据零POST，终止不访问兄弟模型，不关闭思考 |
| tools/probe_k3_equivalence.py | root独占实现，默认Mock20requests/0真实；live须加载PROBE已有授权再走StreamingHTTP；本宽回归包含其8项合成测试，真实效果未测 |
| hermes/chat_agent.py、hermes/v6_agent.py、compare_core_providers.py | 退役实际transport明确失败关闭；离线Fake/Mock算法保留；非dry-run compare CLI拒绝 |
| tests/legacy/production_v5快照 | 冻结历史源未改；外层compare实际入口失败关闭，不复活生产对照 |
| 飞书、部署health、holiday HTTP | 非供应商模型入口，不混入会员用量；本夜未运行 |

代码盘点使用tools/hermes/mingjing_core的client.post/send/stream、requests.post、httpx.post、urlopen、AsyncClient调用点，未只凭Registry宣称覆盖。后台/运行中私有消息至规范ModelPort的P3接线仍须Runtime验收；无真实供应商、中央部署、CI、盲评或网站切换证据。
