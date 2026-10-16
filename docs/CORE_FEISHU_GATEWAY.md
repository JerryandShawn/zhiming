# Core 飞书入口

入口为 `python -m mingjing_core.adapters.feishu_gateway`，依赖 `lark-oapi==1.7.3`（官方 SDK 要求 `websockets>=11,<16`）。SDK 仅接收 `im.message.receive_v1` 中的 `sender_type=user`、`chat_type=p2p`、`message_type=text`。群聊、机器人消息和附件暂不进入 Core。

原始作者 `sender.sender_id.open_id` 必须匹配 PostgreSQL 已有 `feishu` / `user` binding。入口不创建用户、不猜昵称、不自动绑定私聊。原话、稳定 operation 和运行队列在同一事务提交；事件 ID 重投不会增加消息、模型执行或发送。

SDK 回调只提交入站事务；独立异步 worker 执行 `ConsultationService.consult`。恢复轮询读取 PG 入站索引与持久运行，不从 Hermes 历史重新解释。回复必须来自成功运行、有效版本和 `core3.0` 校验 payload；`CoreDeliveryWorker` 原样发送 payload 的 `answer`。无二次模型解释。

上线切换顺序：

1. 先完成本地/隔离 PG 测试、实际身份 binding、Core 配置和网站切换验证。
2. 禁用旧 Hermes 的 Feishu 接收渠道并停止该连接；保留 Hermes 非 Feishu 能力。旧 Feishu Agent 和新入口不能同时收发同一应用。
3. 使用已有 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 与 `ZHIMING_DATABASE_URL`，显式设置 `CORE_FEISHU_ENABLED=true` 后启动新入口。不要在日志、命令参数或版本库里写值。
4. PG 会话 advisory lock 阻止同一 Core 应用启动两个接收进程；这不能替代停止旧 Hermes 渠道。
5. 不自动发送上线探测消息。正常真实用户消息到来后按持久回执核验结果。

发送超时或进程在发送中断时，Outbox 保持 `uncertain`，不能自动重发。只有核验外部消息 ID 与对账 evidence 后才可确认送达或明确未送达。明确拒绝最多使用原 Outbox 的三次尝试，稳定 Feishu UUID 不变。

合成验证：`python -m unittest discover -s tests -p 'test_core_feishu_gateway.py' -v`，需要 `ZHIMING_TEST_DSN` 对应真实隔离 PostgreSQL，测试不会连接 Feishu 或调用模型。

官方 API 依据：[Python SDK WS 示例](https://github.com/larksuite/oapi-sdk-python/blob/v2_main/samples/ws/sample.py)、[官方 Python SDK](https://github.com/larksuite/oapi-sdk-python)。
