# 核心30题操作单（v18：Codex执行真实评测，stage仍由Claude执行）

> v21最新状态：2026-10-24 18:53 +08:00：已执行v21/R20。新冻结候选e708e684109ce50e06c8c172cbcd959d5ee53f2c，同源R11于18:46:50–18:49:49通过48/48、日期7/7、69/69、X02等价、离线core30 30/30；source0f30288760dc7935c22113b2f9c36df66cab393c3ea00295a25bb581785755bf，四原件已核，原81仍71/81及12延期不改。connect真实4/4检查通过，工具2轮/调用1次/额外0次，实际首required/次auto；精确k3.1-pro/high/推理回传及1594字长答通过，计量factor1.15；接入累计8/20含旧4。随后同进程立即启动core30，T05在首POST前被本地LifecycleBinding的旧k3/k3-256k白名单拒绝，映射ledger_unavailable；下游CoreObservation还使用K31批准没有的equivalent属性，尚未走到。core新增真实0、T05 incomplete/score=null，其余未运行，不能记0/30失败；原report和k31_results incomplete保留，key已清，不重试/换control/换账本。唯一安全摘要docs/v4/eval/k31-r20-cb7a00d706f047d4b810a0f62f6ef683.json；代码树不改，待必要新bug裁定。

**v18当前终态：R18真实重跑未通过，保持停止。** 探针修片冻结在`C:/Users/Administrator/Documents/Codex/zhiming-v4-r18` / `e9c82f491f27f69aebdb0f7bfcbc4b63a6e6f26e`，应用代码与d167相同，未改正式树。18:30:44–18:33:40新同源R11通过，source=86769412e90231b7a5b551da9df3dce5fca1ed795e479ea7b0f41cde5a1ec2a9；18:33:56接入因第二次相同工具调用而停止。本轮2次、含v16旧2次累计4/20；两轮均精确k3.1-pro/high/推理存在，2个工具请求，重复的第二个未执行，额外已执行工具0。核心30未启动，key已清，不自动重试或回退。安全摘要`k31-r18-aa6eb26c861e487c877e392e7eb2ba69.json`，唯一新control为probe_k31_aa6eb26c861e487c877e392e7eb2ba69。

需大脑裁定的真实代码事实：K3单工具auto会被safe_tool_choice改成required；原echo的value enum仅允许合成，因此合法的重复工具请求必然同名同参数。本次按R18正确熔断，不把这个受本地策略影响的结果直接当模型不兼容；没有改生产策略或真实schema。下列命令仅保留实际操作接口，当前不得重新执行connect/core30，等待新裁定。

2026-10-24 18:11，北京时间。用户直接授权按指令板v16立即由Codex执行K3.1真实评测；stage仍由Claude执行。本机R17评测专用账本已按大脑脚本首次创建，不代表线上v3额度。最终R11已于18:02:41通过，完整milestone回归在途不再是评测前提；旧v14禁止Codex真实评测的条款已被本次授权替代。禁止换账本或账户绕过供应商停止。

**v16首次历史接入（原件保留）**：18:11:17–18:11:33仅2次真实请求，两次model均精确k3.1-pro/high；K31-TOOLS第二步最终回答断言失败，核心30未启动，key已清。安全摘要为`k31-v16-6cda2856eaaf4b1a9b1226e04b86504e.json`；仅本次v18直接授权允许新control重跑，旧2次仍计总预算。R18失败后不能据这次授权继续建新control重试。

## 候选与原件

最终工作树固定 `C:/Users/Administrator/Documents/Codex/zhiming-v4-formal-integration`，分支v4/integration，冻结SHA `d16730928f263433963a15857e2f0fa6639045e1`。该树private/r11_pending.json定位18:00:00–18:02:41 complete/exit0原件；source为3a23b9c425fe7d1c271da08231c20f666312e76fe4a5d799f87c2f8ce04ae297。根读四份原报告核48/48、7/7、69/69、X02等价及离线30/30；原全81仍71/81十失败，延期与raw incomplete保留。本操作单在开发分支更新，不改变冻结候选源码或复用旧b008门。

旧冻结R11候选为 `b00882cd10e862a0e94103fa97ab263e2a6e18f3`，树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-eval-resume`。13:06–13:08:39原件由该树private/r11_pending.json定位，assessment为同候选private/candidate-eval下R11-080f70697adf4699bad27341809d75b0/assessment.json。原48/48、7/7、69/69、X02等价、离线30/30通过；原全81为71/81，十失败和十二延期/raw incomplete及旧blocked记录保留。13:09已提醒用户降中档/找Claude，不重复提醒。**旧门不批准新源码或新K31真实请求。**

## 现有运行环境与私有配置

Python `C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe`，已安装requirements-core.lock的Core/分词器依赖；Charts独立 `C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-charts/Scripts/python.exe`。业务/控制使用数字回环PG15 55480/core_test_main的隔离schema，不指向stage/生产；评测每题新run/业务schema，控制schema独立probe_前缀。只初始化控制表，不初始化或清空中央账户。

官方公开K3 artifact：`C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023`，代码核固定文件及编码器/依赖。K3.1实际input系数由接入用量校准，旧K3等价证明不授权K31。

Kimi key只从本机现有JSON环境映射读取：`C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/private/claude-eval-k31.env.json`。该文件Git忽略、当前用户/SYSTEM私有DACL；不输出/提交/覆盖/删除正文，也不上传服务器。

按v16/R17，首次精确初始化命令为：上述Core Python加`-X utf8`运行`C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/outputs/明镜台v4_大脑交付/评测/provision_eval_ledger.py`，唯一参数为同目录`member_central_eval.json`。本次已exit0，不再次初始化；schema或JSON存在就保留，不删/重建。该JSON的四个同名MEMBER_*字段仅加载进评测子进程，来自隔离55480/core_test_main、schema member_central_eval、账户kimi-code-member-eval及脚本首次生成的ledger UUID；此处不抄DSN正文。CLI仍核实际PG账户、UUID、位置、停止态，线上v3不使用此账本。

## 1. 只读准备与同源门

以下都是现有CLI和实际字段。首次由主线填最终40位号；R11控制器必须已在该树生成完整原件。命令在同一个正常PowerShell会话执行，PowerShell不打印凭据。换进程时须从已留原件恢复同一control schema、proof和全部报告路径，不能重新生成control schema来绕过已有停止。

```powershell
$FrSha = 'e9c82f491f27f69aebdb0f7bfcbc4b63a6e6f26e'
if ($FrSha -notmatch '^[0-9a-f]{40}$') { throw '最终候选尚未绑定' }
$FrRepo = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-r18'
$FrPython = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe'
$FrTokenizer = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023'
Set-Location $FrRepo
if ((git rev-parse HEAD) -ne $FrSha -or (git status --porcelain -- mingjing_core tools config requirements-core.lock k3-tokenizer.lock.json)) { throw '候选或运行源码clean状态不符' }
$FrPointer = Get-Content 'private/r11_pending.json' -Raw | ConvertFrom-Json
$FrMeta = Get-Content -LiteralPath $FrPointer.metadata_path -Raw | ConvertFrom-Json
if ($FrPointer.candidate -ne $FrSha -or $FrMeta.candidate -ne $FrSha -or $FrMeta.status -ne 'complete' -or $FrMeta.exit_code -ne 0) { throw '最终R11原件未完成' }
$FrGate = Join-Path $FrMeta.output 'assessment.json'
if (-not (Test-Path -LiteralPath $FrGate -PathType Leaf)) { throw 'assessment缺失' }
uv pip check --python $FrPython
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
$FrCentral = Get-Content -LiteralPath 'C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/outputs/明镜台v4_大脑交付/评测/member_central_eval.json' -Raw | ConvertFrom-Json
foreach ($FrName in @('MEMBER_CENTRAL_DSN','MEMBER_CENTRAL_SCHEMA','MEMBER_ACCOUNT_ID','MEMBER_LEDGER_IDENTITY')) {
    if (-not $FrCentral.$FrName) { throw 'R17中央配置字段缺失' }
    [Environment]::SetEnvironmentVariable($FrName, $FrCentral.$FrName, 'Process')
    if (-not [Environment]::GetEnvironmentVariable($FrName,'Process')) { throw "大脑尚未配置受审中央字段：$FrName" }
}
Remove-Variable FrCentral
$FrControl = 'probe_k31_aa6eb26c861e487c877e392e7eb2ba69' # 本次已初始化且失败停止，勿重建/重跑
& $FrPython -m tools.eval.k31_cli init-control --control-schema $FrControl
if ($LASTEXITCODE -ne 0) { throw '控制schema初始化停止' }
& $FrPython -m tools.eval.k31_cli status --control-schema $FrControl
if ($LASTEXITCODE -ne 0) { throw '中央状态检查停止' }
```

status只读0模型；stop_kind非空/in_flight未释放或恢复窗未到就停止。不能因新control schema绕过原中央停止。真正接入前再读新R11四组原报告，实际CLI会再次核同SHA/source/clean/原件及X02契约，不能改JSON或标布尔通过。

## 2. k3.1-pro接入（R18最多6物理，累计授权上限20，含历史旧2次）

仅新裁定允许、中央未停止且同源脚本门全部通过后执行。端口仅OpenAI原生high，每响应核精确k3.1-pro；工具循环2–4请求、连续同名同参数第二次即拒绝，其后输入/长答各1次，最多6次。每POST前核同账户全部候选k31-connect累计不超过20，旧2次不清零；其他两探针未改，不使用旧等价证明。

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
