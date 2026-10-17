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

额度保护策略：如遇额度错误即结束整个夜间真实调用，不重试、不访问兄弟模型。本组未遇额度错误。

初版图片 fixture 的 IDAT CRC 校验失败：两次原400不构成视觉能力结论，已保留在表内并计入调用数；修正后各补一次，两模型通过（同能力合计每模型2次）。`tool_choice=none` 接受请求且不调用工具，但返回仅 reasoning、没有最终文字，因此约束接受与答复可用性分列，初版判定记录见 evidence/P1/probe-initial-36-calls.json。

reasoning 两种回传变体均完成；初版未留签名存在性元数据，不能证明回传必要性。注册表使用已通过的“不回传”路径，不将“可接受一次请求”说成强制协议要求。首事件延迟已记录，首个可见文字延迟未单独计时，不能把 reasoning 延迟当作首字延迟。
