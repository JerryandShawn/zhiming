# P0 实测配置说明

2026-10-17 大脑复核顶部更新及用户明确决定优先：继续使用 Kimi Code 会员端点，主模型和评审都请求 `k3`。这取代此前 `kimi-for-coding` 的配置。P0 同家族评审是阶段提示词的明确要求；不同家族评审放在 P1。

## 接口与模型

密钥只从进程环境读取，不写入配置、仓库、报告或日志。运行子进程可从 Windows 用户环境加载 `KIMI_API_KEY`、`KIMI_BASE_URL`、`KIMI_MODEL`，只检查密钥是否存在，不输出其值。

现有 v3 `ConfiguredModel` 在 base 后追加 `/messages`，所以本次 `KIMI_BASE_URL=https://api.kimi.com/coding/v1`，最终请求 `https://api.kimi.com/coding/v1/messages`。模型配置为 `tools/eval/config.kimi-code.yaml`（v1.1.0）：primary=`k3`、judge=`k3`，运行时 `KIMI_MODEL=k3`。不修改现有 `MingjingCore/3.0` User-Agent、不改业务适配器和业务提示词、不启用第三方追踪。

[2026-10-17 核对的 Kimi Code 官方说明](https://www.kimi.com/code/docs/en/)列出 Anthropic Messages 完整地址及 `k3` 模型 ID，`k3` 的账号可用性取决于会员档位。只有真实响应明确证明档位不支持 `k3` 时，才允许按用户决定退回 `kimi-for-coding`，并在报告记录理由及型号变化；其他 HTTP 错误不能作为改模型依据。请求 ID 不等于供应商不可变权重快照，报告记录请求模型、日期、源码/配置/rubric/endpoint 哈希，P1 再探测版本能力。

## 额度与执行边界

每批至多 10 个场景，逐批记录真实 target / judge 调用次数和耗时；命中额度错误（HTTP 429、usage limit、quota）立即停止整个运行，标记 incomplete，不自动重试、不继续下一批、不降到同一会员其他型号。现有 v3 会丢弃 HTTP 响应正文，因此评测边界对任何 HTTP 错误保守停止，并区分明确 quota 与一般 provider_http_error；不会在报告保存供应商正文。停止后必须等待用户决定何时继续，不能自行执行恢复命令。

Kimi Code 会员额度与用户编程及可能的线上调用共享，用户已知情选择沿用。官方将会员服务定位于编程场景，产品集成推荐开放平台；该风险在复核和更新蓝图中保留。P1 同时支持开放平台备用配置，P0 不操作线上服务或服务器配置。

## 本机运行

已授权在本机隔离 PG 上运行；没有 stage/live 数据访问、生产部署或真实飞书消息。环境加载及调用示例如下，密钥值不会出现在命令中：

```powershell
foreach ($settingName in 'KIMI_API_KEY','KIMI_BASE_URL','KIMI_MODEL') {
    $settingValue = [Environment]::GetEnvironmentVariable($settingName,'User')
    if ($settingValue) { [Environment]::SetEnvironmentVariable($settingName,$settingValue,'Process') }
}
$env:CORE_TEST_DSN = 'postgresql://core_test@127.0.0.1:55480/core_test'
$env:CHART_PYTHON = "$PWD\.venv-charts\Scripts\python.exe"
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:PYTHONUTF8 = '1'
.venv-core\Scripts\python.exe tools/eval/runner.py --mode live --target v3 --model kimi --config tools/eval/config.kimi-code.yaml
```

只有完整 80 场景遍历（44 applicable、36 n/a）、无基础设施/评审错误才生成 `baseline-v3.json`；真实业务失败保留零分。停止时已完成的合成观测和批次调用数保留，未执行项不冒充完成。
