# P8 校准与第二轮追问绑定修复

日期：2026-10-18。只涉及离线证据工作台；真实模型调用 0，数据库写入 0。

## 修复的契约

- 校准记录必须具有合法、唯一的 `(round, alpha)`：第一轮为 `(1, 0.05)`，第二轮为 `(2, 0.025)`。混合轮次、缺少字段、轮次与阈值不匹配均拒绝。
- 同一份 200+200 校准只能覆盖一种 `(candidate_count, event_count)`，避免整体假阳性比例掩盖某一形状的高误报。
- `DeltaCalibration` 显式保存 `round_no`、`alpha`；`covers` 精确匹配轮次、阈值、信号族和样本形状。第二轮缺少自己的独立校准时，其他统计闸门即使通过，也输出“分不出来”。
- 校准数据哈希增加轮次、阈值、信号族、候选数、事件数；对象指纹也包含新增作用域。
- `round2_prompt` 复用 `_validate_bindings`，核对 owner/subject/revision、出生年、截止年、规则版本与哈希。存在不匹配时，在生成问题前拒绝。

## 旧测试修改理由

旧 `raw_nulls` 手写测试记录没有 `round`，此次明确补为第一轮；实际 `assess_statistics` 原本已输出该字段。旧跨 shape 错误断言调整为 `mixed_calibration_shapes`，保留“未见过的事件数不能借用校准”原有保护，并新增“即使两批均见过两种 shape 也拒绝”的反例。这是收紧已确认漏洞的契约，不是修改预期迁就错误实现。

修复前保存的框架/实际图 JSON 若缺少新增轮次字段，不能直接恢复为新版 `DeltaCalibration`。本补丁未修改正式 E-R1 输入、输出、人物选择或规则；补丁验证时已披露的真实计算图为 0/10、全并列，未重跑实际图实验。父线负责统一重跑与现行报告更新。

## 验证

使用现有 Core 环境，清空当前测试进程模型密钥，执行：

```powershell
python -m pytest tests/v4/test_p8_rectification_workbench.py tests/v4/test_p8_rectification_workbench_statistics.py tests/v4/test_p8_rectification_calibration_scope.py -q
```

结果：**71 passed in 0.97s**。包括合法 R1/R2 分别校准、双向跨轮次拒绝、错/缺阈值、布尔/浮点轮次、NaN/Inf、聚合 5% 却某一 shape 100% 的拒绝反例，以及同 scope 不同出生年/截止年/规则缓存的负例。R2 闸门测试刻意使用人工优势向量与替代置换分布，只证明缺少独立校准时必须 abstain，不代表命理信号效度。

四个新增/修改 Python 文件通过 Ruff `E,F,I,B,UP,SIM`、格式检查和 `git diff --check`。统计实现 339 行、最长函数 58 行；独立校验模块 58 行、最长函数 15 行；全部单行不超过 120 字符。

## 未验证与范围

- 未重跑正式实际图实验、完整项目测试或远端 CI，由父线统一执行。
- 未接服务端可信校准读取、会话持久化或权限 API；这些属于主线。
- 本补丁不改变“规则待审、离线统计不证明命理效度”的边界。

父线聚合回归：v4 601/601、脚本80/80；公开固定十人完整CLI及人工矩阵均已重跑。前者仍唯一首名0/10、全部分不出来，人物与规则未改；后者只验证软件框架。现行报告已包含round_no/alpha绑定字段。详见meta-regression-summary.json。
