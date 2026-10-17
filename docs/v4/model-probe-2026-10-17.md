# Kimi Code 模型能力探针

状态：complete；实际调用 38 次。
服务器配置未读取（夜间禁止）；仅本机用户环境的会员端点。客户端标识 MingjingCore/3.0。
未提供其他供应商密钥，未探测。失败/未执行项不得解释为已支持。

| 模型 | 探针/协议 | 通过 | 调用 | 安全错误 |
| --- | --- | --- | --- | --- |
| k3 | text_stream / anthropic_messages | True | 1 | — |
| k3 | single_tool / anthropic_messages | True | 1 | — |
| k3 | tool_choice_auto / anthropic_messages | True | 1 | — |
| k3 | tool_choice_none / anthropic_messages | True | 1 | — |
| k3 | tool_choice_required / anthropic_messages | True | 1 | — |
| k3 | tool_choice_named / anthropic_messages | False | 1 | MODEL_BAD_REQUEST |
| k3 | parallel_tools / anthropic_messages | True | 1 | — |
| k3 | vision / anthropic_messages | False | 1 | MODEL_BAD_REQUEST |
| k3 | schema_default / anthropic_messages | True | 1 | — |
| k3 | schema_examples / anthropic_messages | True | 1 | — |
| k3 | schema_format / anthropic_messages | True | 1 | — |
| k3 | schema_anyOf / anthropic_messages | True | 1 | — |
| k3 | include_usage / openai_compat | True | 1 | — |
| k3 | chinese_long_output / anthropic_messages | True | 1 | — |
| k3 | reasoning_replay_false / anthropic_messages | True | 2 | — |
| k3 | reasoning_replay_true / anthropic_messages | True | 2 | — |
| k3-256k | text_stream / anthropic_messages | True | 1 | — |
| k3-256k | single_tool / anthropic_messages | True | 1 | — |
| k3-256k | tool_choice_auto / anthropic_messages | True | 1 | — |
| k3-256k | tool_choice_none / anthropic_messages | True | 1 | — |
| k3-256k | tool_choice_required / anthropic_messages | True | 1 | — |
| k3-256k | tool_choice_named / anthropic_messages | False | 1 | MODEL_BAD_REQUEST |
| k3-256k | parallel_tools / anthropic_messages | True | 1 | — |
| k3-256k | vision / anthropic_messages | False | 1 | MODEL_BAD_REQUEST |
| k3-256k | schema_default / anthropic_messages | True | 1 | — |
| k3-256k | schema_examples / anthropic_messages | True | 1 | — |
| k3-256k | schema_format / anthropic_messages | True | 1 | — |
| k3-256k | schema_anyOf / anthropic_messages | True | 1 | — |
| k3-256k | include_usage / openai_compat | True | 1 | — |
| k3-256k | chinese_long_output / anthropic_messages | True | 1 | — |
| k3-256k | reasoning_replay_false / anthropic_messages | True | 2 | — |
| k3-256k | reasoning_replay_true / anthropic_messages | True | 2 | — |
| k3 | vision_corrected / anthropic_messages | True | 1 | — |
| k3-256k | vision_corrected / anthropic_messages | True | 1 | — |

官方参考（2026-10-17 核查）：
- https://www.kimi.com/help/kimi-code/models （模型 ID、兼容端点与 k3 约两倍额度说明）
- https://www.kimi.com/code/docs/en/kimi-code/error-reference.html （会员/额度错误）
- https://platform.claude.com/docs/en/build-with-claude/streaming （Messages SSE）
- https://api-docs.deepseek.com/guides/thinking_mode/ （reasoning 回传按能力配置；未实测）

额度错误立即结束整个夜间真实调用，未重试，未访问兄弟模型。
