# P0 实测配置说明

密钥只从当前进程环境读取，不写入配置、仓库、报告或日志。`KIMI_API_KEY` / `MOONSHOT_API_KEY` 至少设置一个；现有 v3 适配器通过 Anthropic-compatible Messages 调用，并在 `KIMI_BASE_URL` 后追加 `/messages`。不修改客户端身份，不启用第三方追踪。

默认 `tools/eval/config.yaml` 固定评审为 `kimi-k3`，沿用 v3 的默认型号。使用 Kimi Code 时可选择 `tools/eval/config.kimi-code.yaml`，它把主模型别名与评审固定为 `kimi-for-coding`。这只是评测运行配置，不改 v3 模型适配器或业务提示词。实际可用性仍以真实调用为准。

Kimi Code 的官方 Messages endpoint 是 `https://api.kimi.com/coding/v1/messages`，因此本仓库适配器对应的 `KIMI_BASE_URL` 应为 `https://api.kimi.com/coding/v1`。该路径与 Claude Code 等自动补 `/v1/messages` 的 SDK Base URL 写法不同。来源：[Kimi Code 官方接入说明](https://www.kimi.com/code/docs/en/)。官方说明 `kimi-for-coding` 为会原位升级的服务别名，所以报告记录请求型号、配置/源码/rubric 哈希与日期；尚不能把它声称为供应商不可变模型快照，P1 应继续核实版本与能力。

如用户在本机设置 Windows 用户环境变量，运行时只在子进程中加载，不把值打印出来：

```powershell
foreach ($settingName in 'KIMI_API_KEY','MOONSHOT_API_KEY','KIMI_BASE_URL','KIMI_MODEL') {
    $settingValue = [Environment]::GetEnvironmentVariable($settingName,'User')
    if ($settingValue) { [Environment]::SetEnvironmentVariable($settingName,$settingValue,'Process') }
}
$env:CORE_TEST_DSN = 'postgresql://core_test@127.0.0.1:55480/core_test'
$env:CHART_PYTHON = "$PWD\.venv-charts\Scripts\python.exe"
$env:LANGSMITH_TRACING = 'false'
$env:PYTHONUTF8 = '1'
.venv-core\Scripts\python.exe tools/eval/runner.py --mode live --target v3 --model kimi --config tools/eval/config.kimi-code.yaml
```

仅使用已经明确授权的真实调用；stage/live 数据库被目标适配器拒绝。供应商/执行/评审异常会使报告标记为 incomplete，不产生 `baseline-v3.json`，不会把配置问题当作能力零分。未收到可用环境配置时不能声称真实模型基线完成。
