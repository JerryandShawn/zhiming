# 普通 chat 接收回执 v1（P4 M4a）

本文描述独立P4候选当前已本机验证的普通chat握手，不是部署或P4整阶段验收。`events_v1.md`、`events_v1.schema.json`、`core4_envelope_v1.md`保持冻结；这里的接收回执是HTTP外层对象，不是core4信封或新公开事件。本文补充`thread_runtime_api_v1.md`中的消息ID；该旧文档关于默认v4 POST命名SSE的临时描述目前仍成立。

## 身份、授权和执行选择

`POST /api/chat`继承现有`X-Token`认证、服务端token→owner绑定及owner/subject授权，不从正文接收owner或凭据。未登录返回401；认证先于Accept解析，所以未登录且Accept畸形仍为401。subject缺省为`self`，必须已获该owner授权；外人run/source/thread不能借猜ID读取或取得回执。

本片没有新增或放宽CSRF/CORS机制：继续依赖现有显式`X-Token`请求头，不改成cookie会话、不提供跨源许可、不接受URL中的token。现应用没有另行签发CSRF token的流程；不能将内容协商或JSON响应宣称为新增CSRF保护。反向代理或部署层既有访问控制仍需原样继承。

运行版本由服务端持久设置选择，缺省v3；**原operation的runtime pin优先于当前owner设置**。Accept仅选择响应格式，不能启用v4、改变lane/预算/深度、安装provider或触发人工模型授权。原先v4的请求即使owner后来改v3也沿原v4身份重放；原先v3请求即使owner后来改v4仍是v3。不得用同request_id保存不同正文、换人物、换来源或把原无痕原话移到人生线程。

v4需已显式注入受信AgentRuntime、计量和已启动dispatcher。缺这些条件时明确失败且不存本轮原话，不回落旧模型。此依赖安装也不等于已获真实请求授权；本机验证只用离线Scripted/FixtureModel，不提供任何真实密钥、DSN或服务器信息。

## 内容协商

请求体仍是JSON对象，`Content-Type: application/json`本身**不会**选择JSON响应。服务器只对明确接受`application/json`、实际runtime=v4的普通chat提供新JSON握手。

每次Accept的所有header值合计最多4096字符、最多32个媒体项；媒体名与参数名大小写不敏感。q为标准0–1，最多3位小数，不接受省略整数位、负数、指数、NaN、Infinity、重复q或非法参数格式。相同表示按最具体媒体范围决定质量，再比较可用表示；显式具体q=0不能被更宽通配恢复。通配、`application/*`或vendor `+json`均不隐式选择JSON握手。

| Accept | 实际v4 | 实际v3 |
| --- | --- | --- |
| 未给、`*/*`、`text/event-stream` | 当前临时命名SSE | 原旧data.type SSE |
| `application/json` | 202 JSON | 406，零写入 |
| `application/json,text/event-stream` | 同最高质量，显式JSON优先 | 原SSE，版本不变 |
| `application/json;q=0.8,text/event-stream;q=1` | SSE | SSE |
| `application/json;q=0,*/*;q=1` | SSE，JSON仍禁用 | SSE |
| `text/event-stream;q=0,*/*;q=1` | 406，SSE不能复活，JSON未opt-in | 406 |
| 只有`application/*`或vendor `+json` | 406 | 406 |
| 非法/重复q、超界、无可用表示 | 固定中文406 | 固定中文406 |

406响应正文是固定对象，不回显header、原话或模型错误：

    {"detail":"请求的响应格式暂不支持，请使用事件流或已配置的 v4 JSON 入口"}

406带`Vary: Accept`、`Cache-Control: no-store`。实际v3 JSON-only会在ensure_owner、图片目录、原话、实体或run写入**之前**拒绝；尚未建立的owner也不会因检查被创建。若同时接受可用SSE，继续原v3路径，而不是自动升级v4。调用方不得把406处理为自动切runtime或自动新建一轮。

## 202接收回执

普通请求仍使用已有稳定request_id；例如以下完全合成输入：

    POST /api/chat
    Accept: application/json
    Content-Type: application/json
    身份头：使用当前已配置的X-Token，不在示例中提供值。

    {"request_id":"synthetic-chat-001","message":"合成示例问题","subject_id":"self","session_id":"shared"}

仅实际v4成功接收后返回202，`Content-Type: application/json`、`Vary: Accept`、`Cache-Control: no-store`。模型无需完成；消息和run事务已经提交，另一连接可读到它们。样例全部为合成ID：

    {
      "run_id":"run_11111111111111111111111111111111",
      "message_id":"msg_22222222222222222222222222222222",
      "thread_id":"life:self",
      "status":"queued",
      "runtime":"v4",
      "run_url":"/api/runs/run_11111111111111111111111111111111",
      "events_url":"/api/runs/run_11111111111111111111111111111111/events"
    }

| 字段 | 权威来源和含义 |
| --- | --- |
| run_id | 当前owner已经持久化的真实run；不是request_id、父run或临时分配值。 |
| message_id | 该run固定的真实当前用户source_message_id；合并多条来源时为持久请求固定的主来源，不是assistant最终消息ID。 |
| thread_id | run与原话实际所属线程；自然语言进入无痕时可能与调用方原先设想的life线程不同。 |
| status | 接收事务读取时的实际状态；普通新轮通常queued，运行中补充可inbox_wait。幂等重放可能已running/succeeded/failed/stale/cancelled/revoked；但已撤来源不获新回执。不是承诺网络响应到达时后台仍处同状态。 |
| runtime | 原run持久pin，当前JSON chat仅v4。 |
| run_url | 同源持久状态入口，继续使用原认证，HTTP完成不等于模型完成。 |
| events_url | 该run真实冻结v1事件入口；继续使用原认证和游标门，不能替换成父run或跨owner URL。 |

回执不包含正文、lease、推理、授权token、私有配置或provider对象。构造时重读PG并核同owner/subject/thread、原话active/current_user/run_context授权、未撤销及当前来源投影；存在source_segments时核其版本/范围。伪造ID、改原话、改范围、跨owner/subject、已撤销/到期来源均不能取得合法回执。

`POST /api/threads/{id}/messages`仍固定返回202，不因Accept自动切版本；本片为它增加同样真实message_id。其实际v4带events_url，v3不冒造冻结事件地址。线程输入不能自己指定runtime/lane/身份。

## 订阅、幂等和状态

收到202后，客户端可以带原认证连接events_url，按冻结`id: seq / event: kind / data: payload`处理。断线时使用最后已处理seq；`Last-Event-ID`、`after`、`after_seq`若同时提供必须规范且一致，包括显式0；非0须在当前owner/run真实事件行存在。取消仍显式调用原`POST /api/runs/{run_id}/cancel`，断开HTTP不是取消。

同request_id跨JSON/SSE重放使用同一原话、run、预算与原runtime，不产生第二次执行。202可能给已终态run的当前状态，不代表自动retry；错误、stale或取消后的重试继续原受保护retry入口和人工规则，不能靠换Accept、新request_id或重新订阅悄悄扩大调用预算。GET run是运行状态权威，GET events只读/幂等修补原公开事件，不另consult。

原默认SSE**本片没有迁移**：实际v4仍是P3临时命名events_v1帧；实际v3仍是旧平面`data:{type:started/context/status/result/error}`与`[DONE]`。因此旧客户端继续使用原行为，但不能据此声称P4要求的默认legacy兼容桥已完成。显式JSON→GET named是当前新客户端可用的明确路径。

## inbox_wait与无痕的跟随限制

运行中补充保存为本消息自己的source和备用子run，202必须返回自己的message_id/run_id与`status: inbox_wait`。该URL真实存在，但不是“父采用后一定在此发final”的承诺：只有真实Journal证明父采用后，备用run才可能被标cancelled；未采用者后续恢复queued执行。本版ACK没有adopted_by、父final跳转或合并跟随协议。客户端不得拿父run冒充本消息，也不得见inbox_wait就自动另建一轮或永久等待它自己的final。采用关系/后续跟随是独立待冻结接口。

自然语言切入无痕后采用实际返回的incognito线程；不把原话重存到life，也不把当前临时模式漏给其它owner/人物/会话。自然语言退出与显式关闭的既有保留/清理规则不变；已关闭、撤销或到期的原来源不得被幂等重建。收据只有身份元数据，不扩大私密历史可见范围。

## 安全错误与仍未接线

认证401、未配置口令503、跨scope403、格式/尚未安装v4/未覆盖复杂输入422、现有版本或幂等冲突409均沿用原错误映射。错误仅给固定或受控中文，不回显私人正文、header或供应商响应。406是本片内容协商拒绝，不是模型拒绝；不得据此发真实模型探针。

普通v4附件、selection、固定draw/reading/report等仍由原入口明确拒绝，不能因为JSON opt-in绕过。既有塔罗reading尚未接专用v4来源与完成桥；原牌阵保留。即时memory_receipt事件生产、旧DOM对core4真实回执的展示、信封外legacy展示投影均未在本片实现；generic PublicReceipt不能冒充具备summary/敏感性/撤销能力的记忆卡。core4信封不得加memory_receipts别名来掩盖前端缺口。

证据：`docs/v4/evidence/P4/2026-10-21-chat-json-acceptance.md`；计划：`docs/v4/execplans/P4_http_compat_20261021.md`。本机80项目标通过只证明该片及原两个明确回归文件，不代表整P4、旧DOM回执、跨线前端接入、真实模型或部署验收。
