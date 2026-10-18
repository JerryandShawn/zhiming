# 契约 v2.2 · 附录 B 扩展数据定义

本目录只保存新版 `docs/v4/07_评测场景集.md` 附录 B 的 **12 项未来契约数据**，对应研究 U4、U5、U7。
它不含执行器、P3 靶标、预制正确回答或已校准的评审配置，没有业务通过率或实测成绩。

`contract.json` 明确：`deterministic-eval-v2.2.0`、`extension_only=true`、
`complete_corpus=false`、`requires_p3_target=true`、`ready_for_live=false`。
本工作树未找到今天正在运行的 v2.1 冻结快照，因此父版本为 `not_found_unbound`，未绑定其哈希。
不能据此推定 v2.1 内容、把此目录称为已冻结的 92 场景全集，或与历史分数直接比较。

## 文件与范围

| 文件 | 用途 |
| --- | --- |
| `contract.json` | 扩展边界、12 个 ID、来源与各场景字节哈希、启用前置条件 |
| `scenario.schema.json` | JSON Schema Draft 2020-12，所有对象禁止未声明字段 |
| `scenarios/A01.yaml`–`A03.yaml` | 猫名、母亲生日、面试公司名未知时不编造 |
| `scenarios/MS01.yaml`–`MS03.yaml` | 跨会话城市目标、购车预算、飞书睡眠信息 |
| `scenarios/KU01.yaml`–`KU02.yaml` | 工作城市与饮食偏好的明确更新 |
| `scenarios/TM01.yaml`–`TM02.yaml` | 从原消息写入开始的相对日期绝对化、跨天或跨月召回 |
| `scenarios/AX01.yaml`–`AX02.yaml` | 反复预测转向行动；同题塔罗先回看、明确坚持后才新抽 |

只有本独立目录新增数据，不修改 `tools/eval/`、原 80 场景、既有 rubric、历史报告或基线。
本目录位于旧 `tools/eval/` 旁边，也不新增 Python，避免改变旧 runner 递归纳入的执行源码。
源文档的九文件同步属于此前的独立提交，本目录不改写它们。

## 输入与来源

每个场景独占一个 `synthetic-v22-*` owner，按设计使用 `default_synthetic` 合成画像与 `Asia/Shanghai`。
`seed.messages` 是有原文、消息 ID、时间、role、channel、session ID 的合成历史，必须通过来源接收路径写入。
只有 user 消息可以支持用户事实；seed 中的 assistant 消息只能是线程历史，不能变成事实来源。
同一 owner 的不同 `session_id` 必须保留为不同话题或会话标签，不得为方便测试合并。
未来靶标应把此字段明确映射到实际 `conversation_id` / `topic_id`；不为跨会话测试新造另一个 owner。
MS01/MS02 的两条来源及当前提问使用三个不同 session；MS03 为飞书来源与网页新会话。

`seed.facts` 被 schema 固定为空。KU01/KU02、TM01/TM02 的事实必须从步骤中的用户原话经真实工具产生，
不能预置正确事实或让靶标在观测时临时推导结果来冒充已存储。
TM01 在 10/15 写入“下周三”，TM02 在 9/30 写入“月底”；两者第二轮都推进到 10/17。
应在写入完成后立即检查 `event_at`、`said_at`、原说法，召回后再次检查，防止把召回日期当作原消息日期。
本扩展的 `event_at` 只有日期，保留 `YYYY-MM-DD` 与日期粒度，按 owner 本地日期比较，不擅自补成午夜。
未来输入含具体时分时，其瞬时才按 UTC 存储，并保留 owner 展示时区。
`said_at` 使用 `entity_instant.same_instant_as` 检查同一消息瞬时，允许 UTC 与原 `+08:00` 的等价表示，
不要求数据库保留带偏移的原字符串。`quote` 与 `original_expression` 单独逐字核对。

AX02 只预置一次已经由合成用户选择并揭示的旧 draw，来源消息和牌面都固定。
第一步经过真实 `tarot_start`，必须返回 `recent_draw_exists`、旧 ID，创建计数为零，旧牌面不变。
第二步提供明确坚持的新来源消息，才允许创建一个不同 ID 的 pending draw；旧 draw 的关键字段仍不变。
新 draw 还需用户点选，不能由模型偷偷选牌或声称新牌已揭示。
这与旧 TA03 的首次重抽预期不同；旧 TA03 原样冻结，此处单独记录新规则。

## 待接入的可观察断言

每一步先冻结消息时间，再通过真实 P3 入站/Agent/工具执行；`expect` 绝不能作为模型或业务服务的输入。
未来靶标应只读导出实际数据库与步骤日志证据，禁止根据预期补造证据或对答案做正则替换。
下面的字段是本扩展的**观测投影约定**，不声称现有数据库或 P3 已实现这些列或接口。
接入时应给出实际持久字段、来源链、状态与投影之间的明确映射；映射不足须标记未验证，不能按零或成功处理。

| 断言 | 检查内容 |
| --- | --- |
| `message_recorded` | 同 owner 的原消息经接收路径持久化，原文、时间、session、channel、role 一致 |
| `entity_count` | 对同 owner 的真实事实或 draw 集合按 `where` 等值筛选，数量等于指定值 |
| `entity_field` | 筛选后必须恰好一个实体，读取其持久化的 `event_at` 或 `original_expression` |
| `entity_instant` | 筛选后恰好一个事实；解析持久化 `said_at`，以 UTC 瞬时和消息时间比较 |
| `source_quote` | active 事实的来源链指向指定 user 消息，原话区间校验通过且等于给定 quote |
| `entity_unchanged` | 恰好一个既有实体，指定字段与 seed 或上一步快照逐项相等 |
| `tool_result` | 实际步骤日志中的 `tarot_start` 返回近期旧 draw 的结果码与正确 ID |
| `tools_forbidden` | 该步实际工具轨迹未调用所列工具；轨迹缺失不视为通过 |
| `draw_creation_count` | 本步操作日志与实际写入中创建的 draw 数，包括之后退役的 draw，等于指定值 |
| `new_draw` | 本步确实只创建一个新 draw，ID 与旧 draw 不同、状态 pending，且属于该 owner |

集合投影仅需这些具名字段：`id`、`owner_id`、`status`、`source_message_id`、`kind`、
事实的 `event_at/said_at/original_expression`，以及 draw 的 `question/created_at/cards`。
来源可能是实际 `source_refs` 列表，投影必须保留各 source ID，不能丢失授权或区间校验。
实体筛选条件全部为等值相与；数量或单实体要求不满足、字段或日志缺失均为失败/未验证，不能跳过。
本目录没有实现或运行上述断言，不把这些数据定义当作数据库业务测试结果。

每个步骤另有 `semantic` 标准和允许查看的证据范围。未来固定的独立评审只能看用户问题、最终答案、
合成来源、实际事实/牌面/工具结果与时钟，不接收受测 system、模型思维或工具执行指令。
这些标准尚未形成绑定模型、schema、rubric 哈希与人工校准的完整评审契约，不能启动 live。

## 数据校验与后续启用

本次只做离线数据校验：Draft 2020-12 元 schema、12 份 YAML、ID/文件名/manifest 哈希，
来源消息与引用完整性、时间单调、跨 session/channel、TM 写入及 AX02 两轮护栏数据结构。
坏 ID、未知字段、无时区时间、非合成 owner、预置事实、伪造来源/日期及绕过坚持步骤应被拒绝。
数据校验通过只表示这些输入定义自洽，**不表示 P3、记忆更新、日期解析或塔罗护栏的业务行为通过**。

启用前必须定位并绑定正确的 v2.1 冻结契约，接入真实隔离 PG 的 P3 靶标及上述证据投影，
固定并校准语义评审配置，再由大脑确认组合后的 v2.2 契约。
将来运行应使用独立报告与恢复目录（例如 `docs/v4/eval/v2.2/`），不得写入现有基线或续跑目录。
schema 中的官方 `$schema` 地址只声明 JSON Schema 方言；本次验证使用已安装库，不联网下载。

在仓库根目录、已具备 PyYAML/jsonschema 的本机 Core 环境中，可用下面的 PowerShell 命令复核严格数据解析。
它只读取本目录，不调用模型或数据库；来源完整性、时间规则及防绕过数据的额外检查见本次证据摘要。

```powershell
@'
import json
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker
p = Path("tools/eval_v22")
s = json.loads((p / "scenario.schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(s)
v = Draft202012Validator(s, format_checker=FormatChecker())
files = sorted((p / "scenarios").glob("*.yaml"))
assert len(files) == 12
for path in files:
    v.validate(yaml.safe_load(path.read_text(encoding="utf-8")))
print("12/12 future data definitions valid; business behavior not run")
'@ | python -B -
```
