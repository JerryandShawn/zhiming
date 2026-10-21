# 线程与补发接线核对（2026-10-21 11:05 +08:00）

只读本工作树已有 Git 对象；没有请求后端、运行模型或合并分支。固定核对对象更新为 `origin/v4/p3-agent-runtime@a83ca8b719597799600a1715e0b097c5b2219e1d`，不外推远端此刻最新状态。其 `docs/v4/contracts/thread_runtime_api_v1.md` 是实际 HTTP 本机候选契约；`mingjing_core/adapters/thread_routes.py`、`thread_events.py` 及 `web.py` 注册已有分支实现，不能把当前缺口称为“契约完全未发布”。本前端分支尚未集成或适配，不代表服务已部署。

| 能力 | 已发布形状 | 前端后续接线要求 |
| --- | --- | --- |
| 线程 | POST/GET `/api/threads`，返回 opaque ID、mode/incognito/status | 用返回的 ID；本地无痕 ID 不冒充服务端资源；close 仅允许无痕 |
| 发消息 | POST `/api/threads/{id}/messages` → 202 JSON，包含 run/thread/runtime/run_url/events_url | 新增集中两步适配；服务端可能改道到无痕，采用回执thread_id，不能把POST直接SSE的executeV3原样换路径 |
| 输入 | message/request_id/subject/conversation/case_ids/depth | 当前候选拒绝附件、tarot/report/selection 等；不得静默丢掉 images 或转普通长期消息 |
| 历史 | `{thread_id,items[]}`，条目含 role/content/at/run/status/incognito/case_ids | 独立公开投影与当前作用域；不直接当成旧 history 数组或 PrivacySession |
| 恢复 | GET `/api/runs/{id}/events`，Last-Event-ID / after_seq、15秒注释心跳 | 复用严格v1解析；可见seq允许撤销缺号，不能原样复用连续策略；422重读run状态，不无限重试坏游标 |
| 排队 | 持久 inbox_wait，Journal/Dispatcher 决定消费 | 不等同当前模拟 QueueAck；item/scope/images 回执仍需显式适配 |
| 取消 | POST `/api/runs/{id}/cancel`，GET run 状态为权威 | 回执不代表已停止；running等权威cancelled。当前inbox_wait未改状态，不能冒称取消排队成功 |

默认 runtime 仍为 v3；普通 HTTP 正文不能启用 v4。后续验证只做集中适配和本机假服务，不改其他工作树、不合并、不访问服务器。

当前a83对象已有`docs/v4/contracts/api_runtime_v1.md`，是前端要求的`api_*.md`发现索引，明确指向线程/事件/core4唯一字段源。此前“两条追踪ref均无api_*.md”的说法不适用于本次对象，现更正。索引明确没有新增画像/记忆/提案/区话题/整理/联系设备/今日端口，也没有冻结NightPort.answer、QueuePort逐项取消或附件协议；不能据此猜端点。`origin/v4/integration@f756731ba8b40be54cf0842d7e590672490ac610` 的旧观察不外推为今天远端状态；v3已有接口继续保留，不能冒充新版聚合端口。

事件 Schema 没有漂移：主线 Schema 与 `web/tests/fixtures/events_v1.schema.json` 的 Git blob 均为 `c84b89f3fb1c58fb0e11797122f9af3470629acd`，原始字节相同。

核对对象：thread 契约 `47004d775eaecd28755055d7a230b2f8b9fafcbd`；router `34ee0c3d3ca6a466a9bce85419de1872805af21f`；SSE bridge `303dbfff8f27be4f58391e8a9514f7797e418c8f`。router/bridge相对08:42固定f492对象没有变化；新增自然语言隐私改道说明，`run_event_read.py`已补终态present_options恢复。内容一致性不替代授权、部署或真实设备验收。

## 输入与接收回执的边界

`SendMessage`只接受`request_id/message/subject_id/conversation_id/case_ids/depth`六个字段。默认self/shared/[]/standard；request_id为1–200个约定ASCII字符，message为1–16000个Unicode码点且不能仅Python str.strip空白；正文和标识不trim或重写。subject/conversation各1–200码点，case_ids为最多8个字符串，不另加逐项非空、长度、唯一性或授权假设。稀疏JS数组必须拒绝，不能every跳洞后展开undefined成为JSON null。

当前线程入口不支持旧ChatPayload的images、selection、draw/session、parent、runtime或owner字段。要在POST前明确拒绝并保留原输入，不能删掉附件再发送，不能把fast猜成deep。无痕不能绑定长期事项；本地校验不代替服务端owner/subject/来源授权。

HTTP必须精确202和application/json，再验证公开run投影；200 SSE、204、HTML、损坏JSON不算已收到。v4要求同一run的相对run_url/events_url；v3没有events_url，不能猜地址或二次POST /api/chat。所有8种实际状态（含inbox_wait及终态幂等回执）均需支持。拒绝外域、query/hash、路径归一化歧义，不把带X-Token的请求交给任意返回URL。

响应thread_id是opaque资源身份，没有请求subject的200字上限；合法200字subject当前会形成205字life线程ID，不能误拒。前端不从life/incognito前缀推断保密或授权，也不要求响应thread_id等于请求线程。首次自然隐私路由后采用返回thread/run归属；未知结果重试仍沿用原目标和request_id，不能改投新线程重发。自然语言退出与立即清正文的close语义不同；此切片不调用close。

## 现有follower不可直接替换路径

`src/chat/followV1.ts`目前把非401/403的HTTP拒绝统一视为可重试unavailable，没有SSE媒体类型核验。其`seq === cursor + 1`连续策略由原测试明确保护；P3 `RunEventReader.page`却先推进数据库游标，再跳过已撤销清空payload的行。冻结契约只承诺递增，因此永久缺号合法，不能无限请求已清正文或合成占位事件。

后续发布端口应显式使用允许缺号的递增策略，保留原演示默认连续策略和断言。事件消费完整成功且归属仍有效后才推进内存游标；重复run/seq去重，心跳不推进，resumed text_reset整段替换。不得把只有数字、没有完整投影的cursor持久化或用于刷新恢复。

422必须停止同一坏游标重连并GET run_url；401/403明确终止或提示登录，瞬时断网/503有限重连。跨retry epoch仍活动时，当前公开投影没有本次起始seq，不能擅自清零重放旧error或自动重发POST。这是待接依赖，先保留已确认投影并显示需核对。终态succeeded的result仍须严格core4校验，不能用宽松legacy解析当证据。

## 停止与所有权

P3 `DispatcherCancellation.request`仅对queued/running写取消标记；queued可立即cancelled，running要流关闭及partial保存后才确认。web路由返回`{ok:true,run_id}`，不代表服务端已停止。后续UI立即显示“正在请求停止”，核回执后GET同一run；只有权威cancelled显示已停止，若竞态succeeded则显示已完成。aborting本地reader或离开页面不发隐式业务取消。

当前inbox_wait不在该request更新条件中，排队消息取消缺权威确认，不能猜DELETE端点或沿用模拟QueueAck声称接通。取消路由也没有读取并验证request_id，不把前端自造cancel标识写成后端幂等证明。

操作显式绑定auth epoch、generation、人物、请求线程、接受后线程/run和signal；发送前、headers getter后、Response后、JSON后及consumer await后都核归属。过期401不能唤起新账号登录提示；忽略signal的迟到Response释放body，不能改投影。错误正文不回显；未知POST结果保留原request_id，不自动重试。

## 下一离线切片（尚未集成或验证）

1. A：纯DTO/202解析，零HTTP、零运行时选择、零存储。严格输入和回执边界，独立测试作者复核205字响应ID及稀疏数组。
2. B：显式注入fetch/auth/scope的submit端口；factory零请求，无默认全局fetch或普通入口实例。先验证恰一次POST→202、归属失效和迟到释放，暂不自动GET SSE。
3. C：独立GET SSE/状态/权威停止适配，解决HTTP分类与递增缺号策略，再用loopback假服务验证两步流程。保留普通executeV3、附件、历史和现有模拟端口。

正式源码/测试/构建仍为61afdbe稳定性受测集合，当前三遍1/3。以上仅只读核对与ignored候选准备，不提前修改普通入口、不启用v4、不发真实模型、不合并、不部署。缺失API仍记录后切换，不等待用户。

## 飞书H5认证的独立依赖

P9 D设计了`POST /api/auth/feishu`交换code、HttpOnly/Secure/SameSite=Lax会话cookie及Origin/CSRF核验；当前a83实际认证仍是X-Token，未发布该路由/会话契约。现有AuthGate和live useChat按token放行，不可用假token、仅检测飞书UA或空token标志冒充cookie免登。后续只能先做独立demo、注入假交换服务和内存会话，不接真实AuthGate、不加载外部SDK、不请求飞书。真实后台配置、一次性code交换及cookie会话接线仍待服务端与用户配置。
