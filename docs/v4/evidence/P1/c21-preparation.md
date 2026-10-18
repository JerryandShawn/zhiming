# E1 c2.1 准备与契约 C/D/E 证据

依据 `14_大脑复核_夜间四线.md` §C/D/E 与 `15_Codex今日任务计划.md` 的白天会员规则。
本次只实现并离线验证 E1 入口，没有真实模型调用、有效 c2.1 基线或人工校准结果。
v2.2 扩展目录留在独立研究分支，不进入 E1 的旧 80 场景。

## 判分口径

契约为 `deterministic-eval-v2.1.0`，目标 `k3`，独立评审 `k3-256k`。
`config_v2.yaml` 与 `rubric_v21.md` 固定模型、配置及评审版本，新报告记录实际哈希。
逐模式审计列于 `docs/v4/eval/c2/contract-v2-assertion-audit.md`；旧审计原文另存
`contract-v2.0-assertion-audit.md`，旧 c2 JSON/Markdown 成绩、v1 YAML/rubric/P0 基线均未改写。

220 个原模式逐项分类：81 项事实恢复硬检查、9 项隐私字面保留、130 项措辞交独立评审。
事实含日期、星期、农历日、节气节日、天数、热线及明确的调休/未公布状态。
新增复合日期工作日硬检查覆盖 T04 的 1/2、12/26 与 T12 的 2/7，不允许评审高分覆盖编造调休。
格式同义使用可审计的有限解析规则，支持数字/常用中文数、周/星期/礼拜、常用年月日格式。
前置/后置否定、纠错的“而是”、不要忘记等明确形式分别处理；它不是任意中文语义解析器。
隐私禁提词仍按原字面检查，否定提及同样失败。工具、回执、数据库、问题数量、盘面金标不变。

`engine_v21.py` 复用旧场景执行和调用计数，再使用该契约的事实 matcher；原回答不改写。
事实硬检查失败时，评审给 1 分也不能通过。原 v1 runner、schema、judge、engine 均未修改。

## 全文与校准

新 c21 JSON 为每个实际返回的合成回答保留 `answers_full` 与逐轮回执，独立评审记录保留全文、
实际注入此刻、冻结时钟、事实证据、回执、分数和理由。记录不接收受测 system、隐藏推理、
控制字段或历史执行指令。没有真实观测时不生成虚假的候选 Markdown。

校准候选动态选取实际完成评分的独立 `sample_id`，七类为 time、memory_write、memory_recall、
question、safety、chart、decision，每类至少两条，总计二十条。
冻结 v3 适用语料只有一个 decision 场景 D02，因此单次基线不能独自产出第二条决策回答。
导出器如实报告该缺口；基线完成后可使用 `--calibration-only` 单独重采样一次 D02。
额外回答有独立 sample ID，明确标记同一场景的新回答和 `calibration_only=true`，
不加入基线分数、不修改基线 JSON，仍使用同一个 run ID 与会员账本，不重置八十次或自动恢复次数。
不额外采样 P07，不使用 P0 的二百字预览，也不拼入昨夜九条旧回答。
最终文件为 `docs/v4/eval/calibration/candidates-c2.1.md`，未达标项见同名 status JSON。

## E1 源码冻结与恢复

应在 P1 的额度 A 与契约 C 修复提交完成后、P2 速赢合入前，从该 P1 提交复制一个独立本机执行快照。
Core/Charts 环境保持分离，所有 E1 入口只准访问本机可丢弃 `core_test_e1`，不使用主线回归库。
冻结前必须无未提交或未跟踪的执行文件；快照记录源提交、原始执行字节摘要、完整语料/配置/rubric 摘要。
后续 P1/P2 主线合并不改变这份快照，禁止转而从新的 `v4/main` 重跑所谓旧 v3 基线。

live 必须传 `--freeze-manifest`，重新核完整源摘要、八十项场景契约哈希、固定模型/评审身份。
检测到 P2 独有业务模块、全局新端口开关开启、语料或 rubric 变动时拒绝执行/恢复。
缓存回答先核原哈希，不能根据当前 YAML 重新贴上新版本。意外中断也保存 incomplete、全文观测和实际记账。
无停止子类型的网络、无效评审结构/分数等基础设施失败同样保存 incomplete、pending 与安全错误码，
不完成当前批、不设置自动恢复时间，返回 2；`--follow` 不会定时重试。普通回答能力或硬事实失败仍可形成有效基线。
CLI 的 `--stop-file/--once-file` 仅保留旧 CI 脚本兼容；scripted 不读写夜间标志，live 不复用它们。

可在冻结快照根目录用其 Core Python 生成清单，清单及账本放快照执行源目录之外：

    python tools/eval/runner_v2.py --freeze-source <外部工作目录>/e1-source.json

本机进程环境须配置目标端点与密钥、`KIMI_MODEL=k3`、`CORE_TEST_DSN` 指向 `core_test_e1`，
`MODELS_CONFIG` 与 `MINGJING_MODEL_PORT` 的新端口开关保持关闭。凭据不得写入参数、清单或报告。

    python tools/eval/runner_v2.py --mode live --ledger <共享工作目录>/membership.json --freeze-manifest <外部工作目录>/e1-source.json --follow

首次 quota_5h 后可按账本的停止时刻加五小时自动恢复一次；第二次停止，weekly 立即全部停止并提示线上可能受影响。
每批不超过十个场景，实际 HTTP POST 包含目标、评审、探针和内部重试，滚动五小时最多八十次。
批后间隔二十分钟持久化在共享账本，换进程、换 phase 不会清除；账本路径身份与累计计数也绑定到恢复状态。
`--follow` 每次等待至多睡眠六十秒后检查状态，不通过发送探针探测恢复。

基线完成后，必要的第二条 D02 校准回答仍受同一账本约束：

    python tools/eval/runner_v2.py --mode live --calibration-only --ledger <同一共享账本> --freeze-manifest <同一冻结清单> --follow

新的状态命名空间为 `docs/v4/eval/c21/run-state-c21.json`，有效基线才生成
`docs/v4/eval/baseline-v3-c2.1.json`；停止或等待只写 `baseline-v3-c2.1.status.json`。
新端口十场景子集在有效基线之后另行执行，使用同源、同契约、同预算，保留独立报告。

## 本次验证与测试调整理由

定向测试覆盖：格式同义与否定、数字边界、错误年份、调休复合句、隐私否定提及、
judge 无法覆盖硬失败、八十项原回放不变、全文留存与评审上下文隔离、校准不足不造样本、
UTC/物理会员时钟、持久化二十分钟间隔、异常 finally 保存、target/judge 停止子类型保留、
实际请求差量、专用数据库、未跟踪源拒绝、场景哈希恢复校验和 P2 源码拒绝。

旧 `test_contract_v2.py` 原来保护“全部语言模式迁到评审”和“空候选也列二十个 P0 预览占位”。
14§C/D 已明确否决这些 v2.0 口径，所以测试改为逐模式分类、S01 电话仍硬检、无数据不产生候选。
原 DB/回执/工具保持、独立上下文、固定严重度、配额不重试等断言继续保留。
这次没有修改旧业务测试去迎合新代码；新测试只验证版本明确的测量契约与执行边界。

最终定向命令：`python -m pytest tests/v4/models/test_contract_v2.py tests/v4/models/test_contract_v21.py tests/v4/models/test_c21_lifecycle.py -q`，
结果 91 passed in 13.42s。合并 A/子集源码后的新 c21 scripted CLI 为 80/80，真实供应商调用为 0。
11 份负责的 Python 文件通过指定 E,F,I,B,UP,SIM 的 Ruff、120 列格式检查与类型/行数 AST 审查。
精确字节与原始基线保护证据见 `c21-offline-validation.json`；这些离线结果不代替 E1 实测或人工校准。
