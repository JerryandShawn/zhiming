# 核心30题评测交接给Claude（代码交接中，尚不能启动真实请求）

按指令板v14，真实接入验证、核心30题及stage均由大脑执行。Codex只做必要代码和离线验证。所有记录为Asia/Shanghai；本单尚未达到可运行真实评测的交付状态，不能用旧批准或手填布尔值绕过以下缺口。

## 当前候选与原件

- 当前R11脚本候选：`b00882cd10e862a0e94103fa97ab263e2a6e18f3`。
- 工作树：`C:/Users/Administrator/Documents/Codex/zhiming-v4-eval-resume`，分支`v4/p3-first-release-r11-20261024`。
- 本次原始运行：`private/r11-run-49dac8e45ad24bfd9312594eaf2efc10/metadata.json`，13:06:00–13:08:39北京，exit0/complete；该树clean并冻结，不重复绿色脚本。
- 已通过派生门：`private/candidate-eval/b00882cd10e862a0e94103fa97ab263e2a6e18f3/R11-080f70697adf4699bad27341809d75b0/assessment.json`。根13:09核四原报告与同源/clean/0外发：48/48、7/7、指定69/69、X02-r11友好/答案保持/重复0写、core30 30/30；原全81为71/81，十个原失败及十二项延期表均保留，原core报告仍incomplete。
- 原c74的四组已完成但控制器误拒保留延期失败的incomplete标签，原blocked及全81原件保留；b008只修此门判定，不改gold。全81中的延期失败继续显示，R11适用69另判。

## 已有本机环境及密钥位置

固定Python：`C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe`；Core依赖已安装，使用仓库`requirements-core.lock`，不自动更新环境。Charts另用`C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-charts/Scripts/python.exe`及`requirements-charts.lock`。现有隔离PG15为数字回环55480/数据库core_test_main，业务评测每题用新隔离schema，不能指向stage/生产。官方K3本地artifact位于`C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023`；K3.1输入计量系数需要按实际用量校准，不能把K3分词器视作已等价。

Kimi环境映射文件：`C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/private/claude-eval-k31.env.json`。这是13:01由当前进程已有凭据准备的JSON环境映射，只含KIMI_API_KEY，文件DACL限定当前Windows用户和SYSTEM，已确认Git忽略。本单只给路径，禁止打印、提交或复制正文到回执。正式入口还需受审的中央MEMBER配置；当前宿主未设置MEMBER_CENTRAL_DSN，不能用业务DSN代替或自动新建账户来放行。

当前可执行的只读准备命令（PowerShell，不发送模型）：

```powershell
$FrPython = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe'
& $FrPython -m pip check
Set-Location 'C:/Users/Administrator/Documents/Codex/zhiming-v4-eval-resume'
Get-Content -LiteralPath 'private/r11-run-49dac8e45ad24bfd9312594eaf2efc10/metadata.json'
```

## 必须补齐后才能提供的真实执行命令

K3.1的离线wire/profile已在release-prep的47d03f7实现：精确k3.1-pro、OpenAI原生显式reasoning_effort=high，实际响应model缺/错即停止；旧default/v3保留。它尚未并入上述R11候选，禁止只给旧候选加载外部分支的新YAML就发请求。

13:09已按v14在本聊天提醒用户：脚本门通过、降低主线思考强度至中档、找Claude接手评测。该提醒不是声明下面的真实运行入口或整个首发包已经完成；当前代码交接仍需补齐。

原`tools.member_delegate`及`tools.eval.live`仍只认旧两模型等价证明；R11新assessment另由新`tools.eval.r11_gate`重读四组原件、核同HEAD/source/X02契约，签发独立K31接入批准。13:19代码a27aab0已推；实际隔离PG/Mock验证接入精确k3.1-pro、跨批/重启最多20物理、每批10、旧模型0POST拒绝，接入批准不能开核心评测。后续源指纹也纳入首发profile，不能把b008旧门套在新代码。真实接入检查CLI、可信核心模型选择、R12整题额度中断及浪费请求记账仍待接线。因此本版不编造尚不存在的真实命令；补齐并固定同源候选后再提供接入及核心30精确分批命令。

## 不能改变的停止和结果规则

主模型及外部评分均须精确k3.1-pro/high，实际每响应检查model。禁止highspeed及off/none/disabled；缺/错model立即停全部评测。单在途1，每批≤10物理请求，正常限速，不伪造TTY/确认/客户端或随机等待。

403 permission_error、usage limit、并发受限、Access terminated任一立即全停；未知reset不试，明确窗口恢复后整题新run/新期限重跑，废请求累计保留；Access terminated永久停等用户。额度中断标incomplete，不算成败；已expired旧run保持0POST，不延长/重签。接入不通过时不自动换模型，由大脑按板决定原计划回退并报告。

R11通过必须同一clean候选具备P3 48/48、日期7/7、原81指定69全过、X02友好/答案保持/重复0写等价断言、core30离线30/30。原81仍可显示延期失败，不改报告凑complete。真实结果需写`docs/v4/eval`的无正文摘要，逐批记录实际物理数/题号/窗口累计；原始正文仅private，不把脚本步数当真实请求。真实接入证明及核心30报告路径/通过判读将在实际CLI接线后补齐，当前均未执行。
