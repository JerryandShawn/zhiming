# P1 / B1 模型端口验证与会员额度备用切换计划

状态：仅计划。2026-10-17 夜间没有访问 stage 或生产，没有读取服务器配置或密钥，没有部署、重启或发送消息。

## 前置与可观察验收

先由大脑验收 P1 草稿 PR，再由用户针对一次具体 stage 验证授权。冻结待验收提交和依赖，使用合成 owner 与独立 stage 数据，核对现有回滚入口。生产当前实际端点尚未确认；早上取得授权后只读 `KIMI_BASE_URL`、`KIMI_MODEL` 两个非密钥值，不读取或打印 Key。

在受保护 stage 配置中设置 `MODELS_CONFIG` 为已验收 YAML 的绝对路径，或设置 `MINGJING_MODEL_PORT=v2`。运行小规模合成问答，检查模型调用元数据中的 provider/model、预算与唯一 submit、owner 隔离和撤销。故障注入用替身，不消耗会员额度；运行时 503 两次切下一供应商，会员额度错误立即排除共享同一密钥的模型，不向兄弟模型重试。若没有其他已配置供应商，返回额度提示，不编造恢复时刻。

端口实测子集 T01–T05、R01–R03、S01–S02 尚未额外运行：夜间仅允许一套 c2 基线。待 c2 基线可用后，由大脑决定是否授权这次同契约兼容比较；不将 v1 的12.16%作为 c2 的相减基准。

## 切换 Kimi 开放平台备用来源

用户保留会员端点作为默认来源。备用来源默认关闭，不自动消耗开放平台账户。

1. 用户本人在服务器受保护配置里写入开放平台 `MOONSHOT_API_KEY`，不写入仓库、聊天或命令行参数；先在获准的 stage 验证，不直接改生产。
2. 在待发布 YAML 中启用 `providers.moonshot.enabled: true`，将 `roles.primary` 的第一项改为 `kimi-open`。它使用 `https://api.moonshot.cn/v1`，当前官方型号参考为 `kimi-k3`；实际能力仍标未探测，必须在单独授权后探测，再开启 tools/vision 等能力。
3. 用合成问答确认 HTTP 协议和真实 provider/model。保留原 YAML 与受保护配置版本，记录切换时间、提交和非密钥端点。
4. 会员额度恢复后是否切回由用户决定。不得修改 User-Agent 冒充其他客户端；当前固定 `MingjingCore/3.0`。

开放平台型号官方参考：[Kimi API 模型选择](https://www.kimi.ai/help/kimi-api/api-model-selection)。会员模型和额度倍率参考：[Kimi Code 模型配置](https://www.kimi.com/help/kimi-code/models)。这些是文档规格，不替代实际能力探测。

## 回滚

撤去 `MODELS_CONFIG` 与 `MINGJING_MODEL_PORT=v2`，按既有授权发布流程恢复旧 `ConfiguredModel` 和原受保护环境值。P1 不改表、不迁移数据，不修改 v3 的预算、校验、流程或业务提示词。回滚后通过持久请求状态核对原 operation，不能把失败请求当作新的业务请求重发。stage 或生产服务操作始终需要用户针对具体批次授权。
