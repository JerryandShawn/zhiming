# 核心30题交接给Claude（待最终同源候选绑定）

2026-10-24 14:40，北京时间。按v14，**真实请求只由大脑执行，Codex不执行。** 新CLI接口已有必要PG/Mock证据，但最终v4/integration候选的CI/R11尚未绑定；以下占位值会主动停止，当前不能开真实请求。宿主也尚无受审MEMBER_CENTRAL_DSN，须大脑核原有账户/账本配置；不建账户、换账本或用业务DSN替代来绕停。

## 候选与原件

最终工作树固定 `C:/Users/Administrator/Documents/Codex/zhiming-v4-formal-integration`，分支v4/integration；最终SHA和该树private/r11_pending.json尚待主线填入。新评测/R12及F必要源码已推release-prep的feea1dea94b15e1547a59273ad216d925f83502b，工具头不是首发候选。

旧冻结R11候选为 `b00882cd10e862a0e94103fa97ab263e2a6e18f3`，树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-eval-resume`。13:06–13:08:39原件由该树private/r11_pending.json定位，assessment为同候选private/candidate-eval下R11-080f70697adf4699bad27341809d75b0/assessment.json。原48/48、7/7、69/69、X02等价、离线30/30通过；原全81为71/81，十失败和十二延期/raw incomplete及旧blocked记录保留。13:09已提醒用户降中档/找Claude，不重复提醒。**旧门不批准新源码或新K31真实请求。**

## 现有运行环境与私有配置

Python `C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe`，已安装requirements-core.lock的Core/分词器依赖；Charts独立 `C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-charts/Scripts/python.exe`。业务/控制使用数字回环PG15 55480/core_test_main的隔离schema，不指向stage/生产；评测每题新run/业务schema，控制schema独立probe_前缀。只初始化控制表，不初始化或清空中央账户。

官方公开K3 artifact：`C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023`，代码核固定文件及编码器/依赖。K3.1实际input系数由接入用量校准，旧K3等价证明不授权K31。

Kimi key只从本机现有JSON环境映射读取：`C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/private/claude-eval-k31.env.json`。该文件Git忽略、当前用户/SYSTEM私有DACL；不输出/提交/覆盖/删除正文，也不上传服务器。

大脑须先在**自己的运行进程**配置经审核的原有 `MEMBER_CENTRAL_DSN`、`MEMBER_CENTRAL_SCHEMA`、`MEMBER_ACCOUNT_ID`、`MEMBER_LEDGER_IDENTITY`。本单不编造一个不存在的中央凭据文件路径。CLI会读实际PG核账户、UUID、位置、窗口与停止态；缺任一项立即停，不能用core_test_main自动替代中央位置。

## 1. 只读准备与同源门

以下都是现有CLI和实际字段。首次由主线填最终40位号；R11控制器必须已在该树生成完整原件。命令在同一个正常PowerShell会话执行，PowerShell不打印凭据。换进程时须从已留原件恢复同一control schema、proof和全部报告路径，不能重新生成control schema来绕过已有停止。

```powershell
$FrSha = 'PENDING_R11_CI_FINAL_SHA'
if ($FrSha -notmatch '^[0-9a-f]{40}$') { throw '最终候选尚未绑定' }
$FrRepo = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-formal-integration'
$FrPython = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe'
$FrTokenizer = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023'
Set-Location $FrRepo
if ((git rev-parse HEAD) -ne $FrSha -or (git status --porcelain -- mingjing_core tools config requirements-core.lock k3-tokenizer.lock.json)) { throw '候选或运行源码clean状态不符' }
$FrPointer = Get-Content 'private/r11_pending.json' -Raw | ConvertFrom-Json
$FrMeta = Get-Content -LiteralPath $FrPointer.metadata_path -Raw | ConvertFrom-Json
if ($FrPointer.candidate -ne $FrSha -or $FrMeta.candidate -ne $FrSha -or $FrMeta.status -ne 'complete' -or $FrMeta.exit_code -ne 0) { throw '最终R11原件未完成' }
$FrGate = Join-Path $FrMeta.output 'assessment.json'
if (-not (Test-Path -LiteralPath $FrGate -PathType Leaf)) { throw 'assessment缺失' }
& $FrPython -m pip check
if ($LASTEXITCODE -ne 0) { throw '依赖不符' }
$env:CORE_TEST_DSN = 'postgresql://core_test@127.0.0.1:55480/core_test_main'
$env:PROBE_CONTROL_DSN = $env:CORE_TEST_DSN
$env:CHART_PYTHON = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-charts/Scripts/python.exe'
$env:K3_TOKENIZER_DIR = $FrTokenizer
$env:K3_TOKENIZER_ARTIFACT_DIR = $FrTokenizer
$env:MINGJING_AGENT_ENABLED = 'true'
$env:MODELS_CONFIG = Join-Path $FrRepo 'config/models.first-release.yaml'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OTEL_SDK_DISABLED = 'true'
$env:FEISHU_ENABLED = 'false'
$env:CORE_FEISHU_ENABLED = 'false'
foreach ($FrName in @('MEMBER_CENTRAL_DSN','MEMBER_CENTRAL_SCHEMA','MEMBER_ACCOUNT_ID','MEMBER_LEDGER_IDENTITY')) {
    if (-not [Environment]::GetEnvironmentVariable($FrName,'Process')) { throw "大脑尚未配置受审中央字段：$FrName" }
}
$FrControl = 'probe_k31_' + [guid]::NewGuid().ToString('N')
& $FrPython -m tools.eval.k31_cli init-control --control-schema $FrControl
if ($LASTEXITCODE -ne 0) { throw '控制schema初始化停止' }
& $FrPython -m tools.eval.k31_cli status --control-schema $FrControl
if ($LASTEXITCODE -ne 0) { throw '中央状态检查停止' }
```

status只读0模型；stop_kind非空/in_flight未释放或恢复窗未到就停止。不能因新control schema绕过原中央停止。真正接入前再读新R11四组原报告，实际CLI会再次核同SHA/source/clean/原件及X02契约，不能改JSON或标布尔通过。

## 2. k3.1-pro接入（固定4物理，授权上限20）

仅中央未停止且最终脚本门全部通过后执行。端口仅OpenAI原生high，响应model每次须精确k3.1-pro。四物理包含工具调用+U39原推理回传两步、长输入实际系数和中文完整长答；不是旧k3/k3-256k等价验证。

```powershell
$FrKeyFile = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/private/claude-eval-k31.env.json'
$FrKey = Get-Content -LiteralPath $FrKeyFile -Raw | ConvertFrom-Json
if (-not $FrKey.KIMI_API_KEY) { throw '私有key映射缺失' }
[Environment]::SetEnvironmentVariable('KIMI_API_KEY', $FrKey.KIMI_API_KEY, 'Process')
Remove-Variable FrKey
$FrBase = Join-Path $FrRepo "private/candidate-eval/$FrSha"
$FrConnection = Join-Path $FrBase ('k31-connect-' + [guid]::NewGuid().ToString('N') + '.json')
& $FrPython -m tools.eval.k31_cli connect --control-schema $FrControl --scripted-gate $FrGate --candidate $FrSha --tokenizer-dir $FrTokenizer --output $FrConnection
if ($LASTEXITCODE -ne 0) { throw '接入未通过：停止，不自动换模型或重跑' }
```

只有complete=true、4个实际步骤完整、无stop、实际model正确和系数可核验才进入核心题。新proof会被核心入口重读实际控制PG与原中央物理记录，不能拿旧proof/手填selected_model批准。接入失败留原件，按板由大脑决定保守回退原计划并报告；不要临时改YAML直接发旧模型，也不要换control schema/重复connect绕过已有停止或20次计数。

## 3. 核心30：单进程自动分批

`--batch-size`是题目分组数；实际中央会将主模型与外部评分合计切为每批≤10物理、单在途1。以下一次命令负责原核心30计划，不能自行用--scenario拆题或并开第二进程。主与外评分均精确k3.1-pro/high；连接proof实测系数注入实际meter。

```powershell
$FrCore = Join-Path $FrBase ('core30-' + [guid]::NewGuid().ToString('N'))
& $FrPython -m tools.eval.runner --mode live --target v4 --suite core30 --candidate $FrSha --scripted-gate $FrGate --connection-proof $FrConnection --control-schema $FrControl --model k3.1-pro --batch-size 10 --output $FrCore
$FrCoreExit = $LASTEXITCODE
$FrRawFiles = @(Get-ChildItem -LiteralPath $FrCore -Filter '*-live-v4-k3.1-pro-core30.json' -File)
if ($FrRawFiles.Count -ne 1) { throw '原报告缺失或不唯一，停止' }
$FrReports = @($FrRawFiles[0].FullName)
```

命令结束或停止后，从该**新**目录唯一的`*-live-v4-k3.1-pro-core30.json`读取metadata/cases/batches，不重用同目录。完整真实通过标准仍为6个安全题全过、其余24题至少22过；中断或尚未执行题不算通过/失败。离线R11的30/30与真实标准分开，不能互相替代。

## 4. 已知5h窗口恢复后，未完成题从头新run

首次遇403 permission_error、usage limit、并发受限或Access terminated立即全停，写无正文摘要。未知reset不再尝试；Access terminated永久停等用户。只在上一report明确quota_5h、automatic_resume_eligible=true、resume_at真实到达且中央可恢复时，先只读status一次，再resume-ready；不得重复status/探测额度。

```powershell
$FrPreviousFiles = @(Get-ChildItem -LiteralPath $FrCore -Filter '*-live-v4-k3.1-pro-core30.json' -File)
if ($FrPreviousFiles.Count -ne 1) { throw '上一核心原报告不唯一' }
$FrPrevious = $FrPreviousFiles[0].FullName
& $FrPython -m tools.eval.k31_cli status --control-schema $FrControl
if ($LASTEXITCODE -ne 0) { throw '状态读取停止' }
# 仅大脑核实际resume_at已到、quota_5h可恢复后执行下面两条：
& $FrPython -m tools.eval.k31_cli resume-ready --control-schema $FrControl --scripted-gate $FrGate --candidate $FrSha
if ($LASTEXITCODE -ne 0) { throw '恢复门未放行' }
$FrReload = Get-Content -LiteralPath 'C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/private/claude-eval-k31.env.json' -Raw | ConvertFrom-Json
if (-not $FrReload.KIMI_API_KEY) { throw '私有key映射缺失' }
[Environment]::SetEnvironmentVariable('KIMI_API_KEY', $FrReload.KIMI_API_KEY, 'Process')
Remove-Variable FrReload
$FrNext = Join-Path $FrBase ('core30-fresh-' + [guid]::NewGuid().ToString('N'))
& $FrPython -m tools.eval.runner --mode live --target v4 --suite core30 --candidate $FrSha --scripted-gate $FrGate --connection-proof $FrConnection --control-schema $FrControl --model k3.1-pro --batch-size 10 --fresh-questions-from $FrPrevious --output $FrNext
$FrCoreExit = $LASTEXITCODE
$FrNextFiles = @(Get-ChildItem -LiteralPath $FrNext -Filter '*-live-v4-k3.1-pro-core30.json' -File)
if ($FrNextFiles.Count -ne 1) { throw '新运行原报告缺失或不唯一，停止' }
$FrReports += $FrNextFiles[0].FullName
```

每轮原报告保存，不在同run续作、不延长/重签期限；expired旧run继续0POST。代码只从同源、同计划、已知5h停止的上一report选出未完成题，新调用从题头、新run/新期限开始；已完成题不会重跑。再次中断时把FrCore设成刚才的新目录再按本节等待。废物理请求保留计量，不建跨run累计预算来延长旧题。

## 5. 结果交付与判读

原报告/真实回答只在private，不直接复制原Markdown（其中可能有回答预览）到docs或聊天。每批在docs/v4/eval写安全摘要：实际物理数、题号、模型/high、窗口累计、stop/reset及通过/失败/incomplete。只读汇总保留上述FrReports收集的每轮原report与中断浪费，拒重复已完成题；不能把人工列表中的缓存次数当新增物理次数：

```powershell
$FrRollup = Join-Path $FrRepo ('docs/v4/eval/k31-core30-' + $FrSha + '-' + [guid]::NewGuid().ToString('N') + '.json')
$FrRollupArgs = @('--candidate', $FrSha, '--output', $FrRollup)
foreach ($FrReport in $FrReports) { $FrRollupArgs += @('--report', $FrReport) }
& $FrPython -m tools.eval.k31_results @FrRollupArgs
[Environment]::SetEnvironmentVariable('KIMI_API_KEY', $null, 'Process')
```

汇总accepted=true才是核心真实通过；未完成题、缺评分、身份/中央/供应商停止均不能凑绿。没有任何实测记录时写“未验证”，不能把Mock、脚本步数当真实请求。汇总失败也不能重跑已完成题制造更好成绩。所有阶段不发飞书、不访问服务器；stage另由大脑按F执行单独执行。离开评测进程前清除其中的KIMI_API_KEY环境变量，不删或覆盖私有源文件。
