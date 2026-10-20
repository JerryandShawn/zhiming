# P1b 中央守卫接线第一切片（阶段未完成）

时间：2026-10-20 23:27，北京时间（Asia/Shanghai，+08:00）。真实供应商请求 0、服务器访问 0、飞书发送 0。

本切片把双协议 `StreamingHTTP` 的每一次物理发送与重试接到既有真实 PG `QuotaGuard`。顺序为最终 HTTP JSON 构建 → 原请求体积检查 → 中央 acquire / reserve → 既有计数钩子 → send；permit 持有到 SSE/response 结束。每次重试单独计账；错误、取消、consumer close 均释放 session slot，已观察到的额度/并发/Access terminated 同步写持久停止，后续零 POST。consumer 在完整响应结束前关闭时保守记 unknown，不退款，不宣称服务器已收/未收。

中央位置必须显式设置四个独立环境字段：`MEMBER_CENTRAL_DSN`、`MEMBER_CENTRAL_SCHEMA`、`MEMBER_ACCOUNT_ID`、`MEMBER_LEDGER_IDENTITY`。运行时仅验证现有账号与固定 UUID / PG 位置，不创建表或账号，不回退业务 DSN。异常和 repr 不包含 DSN。真实会员传输缺位置即失败关闭。已明确使用 `httpx.MockTransport` 的纯协议测试不可能发送真实 HTTP，故可没有中央配置；守卫集成测试显式传真实 PG guard，另用独立 HTTP transport 替身证明环境装载路径也经过真实中央 PG。

角色取端口构造时绑定快照；请求 `role` 参数不能更换它。Registry 给会员 handle 绑定角色，双协议在 wire 策略前验证，保留 U39 的 high/default、完整推理回传、禁关思考和原体积闸门。运行 scope 为应用侧 ContextVar，提供 lane/run/batch/scenario，模型正文、headers 和环境角色不能给它授权；eval/probe 缺当前活动批次会被中央 PG 拒绝。API 使用 `call_scope(CallScope(...))`；并发任务使用独立 scope，退出恢复。

Anthropic 与 OpenAI 的 input/output/cache 字段在 permit 内归一记录；未知 token 保持 null。OpenAI `prompt_tokens_details.cached_tokens` 以前会被 `safe_usage` 丢弃，本切片保留为 `cache_read_tokens`，不保存任何正文或推理。

## 当前物理入口盘点

| 入口 | 当前状态 |
| --- | --- |
| `OpenAICompat`、`AnthropicMessages` → `StreamingHTTP._request` | 已接中央守卫，直接构造、Registry、PortBackedModel 共用；每次 adapter / Registry 重试独立 acquire |
| `mingjing_core/adapters/model.py` 的旧 `ConfiguredModel` | 尚缺，下一切片接线；本切片不宣称 E1/v3 已全覆盖 |
| `tools/eval/runner_v2.py` / subset / EvidenceJudge | 新端口底层已受守卫约束；旧 ConfiguredModel、可信 eval scope 与人工启动 CLI 尚缺 |
| `tools/probe_models.py` | 新端口底层已受守卫约束；可信 probe scope、人工开始和≤20等价脚本尚缺 |
| `hermes/chat_agent.py`、`hermes/v6_agent.py` 与旧生产 compare | 退役/对照入口尚待显式拒绝；不得复活，不因本切片放行 |
| Feishu、health、holiday HTTP | 不是供应商模型请求，不纳入 Kimi 账号预算；本夜未执行 |

只有 membership 提供方使用该会员账号预算；非会员旧契约保留，不伪称其他账号消耗同一个会员窗口。已知 Kimi Code endpoint/provider 即使漏设 membership 也启用守卫。

## 实际验证

使用 P2 Core 解释器，当前 P1b 工作树，本机 PG15 / core_test_main / 回环 55480，每例独立现有 p2_test schema；清除供应商密钥和追踪配置，仅 HTTP 用替身，中央 quota 业务和 PG 不替代。

最终目标命令覆盖新 `test_quota_http_pg.py`、`test_quota_http_boundary.py` 与既有 protocols、request_policy_wire、request_policy_size、u39_policy_wire、registry_retry_ownership、error_actions_transport：**295 passed / 6.13s**。新增 18 项包括 13 项真实 PG，证明逐次4重试4行、成功用量、两 slot 同持、第三拒绝、关闭/取消释放、HTTP/SSE终止持久全停、eval无批拒绝、critic份额、真实中央环境装载、体积零PG/零POST及角色零POST拒绝。Ruff 指定 E/F/I/B/UP/SIM 规则通过，新增文件 format 通过；没有启动模型实测。

首轮角色硬绑定后旧 U39 参数化夹具 10 失败 / 194 通过，未计绿。该夹具原用默认 primary 构造后在 complete 切角色，保护意图为六角色的 high/default wire。按当前可信角色裁定，只补 `role_binding=role` 构造字段，所有原 effort/wire/metadata 断言保留；新增 runtime 改角色零 POST 反例。原因已写 ExecPlan Decision Log。

本切片没有新增迁移、没有变更0008、没有修改已有 quota 核心/双槽策略，不创建新共享库。未完成项为上表旧入口、人工启动、探针等价、完整回归/CI、真实供应商与部署；P1b 仍未完成。
