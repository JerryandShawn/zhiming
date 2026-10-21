# API：线程、运行与事件接入索引 v1

2026-10-21，北京时间。本文为前端线的`api_*.md`发现入口；字段的唯一真相源仍是[线程运行契约](thread_runtime_api_v1.md)、[事件v1](events_v1.md)、[事件Schema](events_v1.schema.json)和[core4信封](core4_envelope_v1.md)。不复制第二套事件类型。当前仅本机显式安装v4的验证候选，默认线上仍v3；没有部署或真实模型验收。

## 已有后端入口

沿用现有`X-Token`认证；owner只来自认证。资源ID使用响应返回的值，不从标题或前端演示ID推导。所有线程请求结构严格拒绝未知字段，不能传provider、runtime、lane或可信角色。

| 入口 | 前端用途 | 必须保留的语义 |
| --- | --- | --- |
| `POST /api/threads`、`GET /api/threads` | 建立/列出人生或无痕线程 | 无痕需要已安装v4；人生线程不提供立即删除接口 |
| `POST /api/threads/{id}/messages` | 提交一条消息/运行中插话 | 202返回真实run_id/thread_id；以返回thread_id为准，自然无痕路由可能改变线程 |
| `GET /api/threads/{id}/messages` | 指定线程历史 | 不以全局history代替无痕历史；不返回推理；关闭/到期正文不能恢复 |
| `POST /api/threads/{id}/close` | 立即清理无痕线程 | 幂等，关闭后重放不重建；“结束无痕”自然指令与立即清正文语义不同 |
| `GET /api/runs/{id}` | 回查持久状态和已提交信封 | 持久PG状态为权威；未提交partial不是已验证final |
| `GET /api/runs/{id}/events` | v4订阅/断线补发 | `Last-Event-ID`/after_seq、run_id+seq去重；读取SSE的event名，不套用旧data.type协议 |
| `POST /api/runs/{id}/cancel` | 显式停止运行 | 写取消请求后等待实际worker停止；HTTP断开本身不取消，接口200不等于已经完成两秒内停止 |

消息正文为1–16000字；case_ids最多8项，无痕不接受长期case_ids；depth为standard/deep。完整输入、状态码、稳定request_id和响应字段以线程运行契约为准。一次请求的重试继续使用同一身份和原载荷；修改载荷必须作为新操作，不能把重放冲突转成成功。

## 与前端night端口的明确差额

只读核对前端固定`cb1213d656f77f17e337916d5cf8eb497125ad29`的`night/port.ts`、`queue/port.ts`、`recovery/port.ts`、`privacy/port.ts`。这些仍是本地演示端口，本文没有修改它们或宣称已经替换。

`PrivatePort.respond`可在后续适配器按“建无痕线程→提交→订阅→回查”对接上述入口，但其images字段目前不被v4线程入口支持；不要丢掉附件后假装已提交。前端只投影text_delta/text_reset/final时，也不能丢弃最终core4回执或把partial显示为已验证结果。

`RecoveryPort`的本地fixture不是`/api/runs/{id}/events`；真实适配器须保留认证、稳定run和最后实际消费游标。模块SSE hub及24小时清理仍待P4接入，当前后端是PG游标读取/轮询适配。

`QueuePort`的scope_id/item_id/after_run_id/images与撤销待发消息命令还没有逐字段冻结的独立API。现有线程POST会持久入inbox_wait，但不等于QueuePort完整等价；取消整个run也不等于撤回某条尚未采用的插话。继续保留模拟端口，不能编造`/api/inbox`已存在。

`NightPort.answer`的askId/optionIds确认不能直接映射旧`/api/runs/{id}/resume`：旧端口使用interrupt_id/state_version/parent_run，不是冻结asked_id能力协议；v4复杂parent_run输入目前前置拒绝。后续确认API须单独冻结与授权校验。记忆、画像、提案、设备、主动联系、今日页、区与话题仍按P5/P5b/P7/P10逐个交真实API契约，不把本索引当全量端口完成。

## 证据与待验证

实现位于`adapters/thread_routes.py`、`thread_events.py`及`web.py`的运行回查/取消路由；本机PG路由边界见`tests/v4/agent/test_thread_routes_pg.py`和`2026-10-21-runtime-api.md`证据。本文仅校对代码和已有契约，没有新增测试或复用旧数字宣布新行为通过。

08点固定9a6f882d完整v4仍有1项case_update幂等失败、旧DOM回执严格xfail；M8原46/47。P1b/P3组合、精确新头Linux、真实前端HTTP全流程、服务器启用与真实模型质量分别待验。没有新增字段、路由、依赖或迁移，没有修改其他线文件。
