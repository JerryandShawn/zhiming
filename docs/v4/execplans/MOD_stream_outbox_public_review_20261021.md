# MOD：审查旧流式公开输入与 core3 兼容边界

本 ExecPlan 遵循 `.agent/PLANS.md`。只新增本轮文件，不修改前轮 150 项独立验收、产品或黄金材料。

## Purpose / Big Picture

补审可由真实持久化数据进入的公开恢复和结果投影，防止兼容旧 core3 结果时漏掉当前主体绑定。
不为了覆盖内部二次校验构造不可能的私有状态；模型、网络、数据库、业务调用均为零。

## Context and Orientation

工作目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
复用 `stream_outbox_v2/freshness.py::FreshnessEvidence/validate_freshness`，
`transitions.py::claim/begin_dispatch`，`codec.py::restore_state` 和显式 Clock。
旧 core3 最终结果经 `adapters/channels/hermes.py::validated_payload` 校验，模型字段为
`domain/consultation.py::FinalAnswer`；本轮不会实例化 Hermes 适配器或打开其数据文件。
蓝图 §16 要求 owner/subject 隔离；Q6 接线文档要求完整已校验结果与当前来源，不得因为读取旧版本而放松。

## Progress

- [x] (2026-10-21 09:37 +08:00) 读取指令板 v1、七产品历史覆盖、core3 展示校验和前轮测试。
- [x] (2026-10-21 09:38 +08:00) 原 12 项首跑 2 failed/10 passed，立即保存反例与原七源 SHA 并通知 root。
- [x] (2026-10-21 09:39 +08:00) root 明确授权仅 core3 分支补 subject 核对；12 原真值通过/0.12s。
- [x] (2026-10-21 09:39 +08:00) 两 P9 兼容套件 1967 passed/11.80s；七源与完整套件前后 SHA 相同。
- [x] (2026-10-21 09:40 +08:00) 本轮提前冻结；09:44 起保持所有产品/测试/fixture 不变，等待 root 明确通知全量结束。

## Surprises & Discoveries

core4 freshness 显式比对 envelope.meta.subject_id，core3 分支目前仅比对 run_id。
`validated_payload` 会检查 core3 展示必填字段、成功校验与 run dependencies，但没有主体一致性比较。
合成公开反例确认：明确 foreign subject 的完整 core3 结果在 claim 与 dispatch 都未被拒绝，
首跑 2 failed/10 passed。不是已观察到真实泄漏；没有真实平台或 PG 调用。

## Decision Log

独立真值：相同 host scope 和 run_id 不应使一个明确声明 foreign subject_id 的 payload 变成可投递。
同时保留正确 subject 的完整 core3 正例，不能以关闭旧版本兼容来变绿。
Clock 的 naive 返回值应受控拒绝；时钟倒退缺少历史观察字段，暂只记接线风险，不擅自新增时间政策。
09:44 起所有产品/测试/fixture 冻结，不自行按 elapsed time 放行。
root 明确要求优先修真实缺口而不隐藏失败，授权本子任务唯一修改 freshness.py 的 core3 分支。
保留 validated_payload、run、epoch、manifest 和两个 freshness 边界；只补 meta.subject_id 与当前 scope 等价校验，
采用 core4 既有 `validated_subject_mismatch` 原因码。新测试仅由 Ruff 整理 import，原语义断言不变。

## Outcomes & Retrospective

12 独立目标与 1967 兼容目标通过；完整正确 core3 仍可领取/发送，错误主体在两个边界均拒绝。
错误 run/空 dependencies、naive Clock、Tokyo 同瞬间控制也通过。相对首失败七产品，仅 freshness.py 变化。
旧七文件覆盖的部分遗漏是构造之后的重复校验，不强造非法对象执行。本轮未重跑 coverage；
前轮覆盖报告保持旧哈希下的历史观察，不作为修后源码的当前覆盖声明。
本轮在冻结前结束，待 root 纳入 09:45 全量；不把本地目标通过称为 CI、部署或真实数据隔离已验收。

## Plan of Work

新增唯一 `tests/v4/p9_v2/test_public_inputs_review_acceptance_mod.py`，显式虚构完整 core3 输入，
覆盖正确主体、错误主体、错误 run、空 dependencies 和 naive Clock；均通过公开入口。
新增审查/失败证据，区分静态风险、实际反例和真实部署未验证。

## Concrete Steps

root 允许的单进程目标命令，在本工作目录运行：

    python -m pytest tests/v4/p9_v2/test_public_inputs_review_acceptance_mod.py -q --tb=short

Core 解释器为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe`。
清除 provider keys、关闭 tracing、禁止 socket；TEMP/TMP 仍在本树 private/mod-week/tmp。

## Validation and Acceptance

沿用 07 场景 X08 核心续写和 F03 来源隔离约束，不宣称完成 PG/通知链验收。
完整有效 core3 在正确 scope 可领取和发送；明确 foreign subject 或 wrong run 的结果不能授权任一边界。
错误 Clock 不得被本机时区暗中解释。反例保留原失败和 source SHA，不改既有真值。

## Idempotence and Recovery

全部输入虚构且进程内，重复执行无业务写入。产品修复由 root 决定；冻结窗口中只保留明确断点。

## Artifacts and Notes

本轮新文件以 `STREAM_OUTBOX_public_review_20261021` 标识；不覆盖前轮任何报告。
不读 Q5 B、校准 75 条正文或个人原始资料，不执行 Git。
首失败证据：`STREAM_OUTBOX_public_review_failure_20261021.json`，SHA-256
`25ec73577731c3ff91bcc363b0aebed73ff41e1b260834186a61a168c192a220`。
修后兼容证据：`STREAM_OUTBOX_public_review_verification_20261021.json`，SHA-256
`d5f07884643997e3b72860fbad8f5234a8aa247d847ef06be0632a9c1ade512d`。
freshness.py 修后 SHA-256：`85c509b6343d7e72d46fad2f35133e54816d9aa399611fcab47c791ba617d38f`。
接线说明：`docs/v4/integration/mod/STREAM_OUTBOX_core3_subject_20261021.md`，明确 core3 主体不能缺失或跨主体，
scope/run 自洽不够；历史缺失数据不能从当前请求猜填。

## Interfaces and Dependencies

没有新增产品 API、依赖、Schema 或迁移。pure host evidence 只能核对一致性，不认证实际 PG 当前状态。

## 修订记录

- 2026-10-21 09:37 +08:00：创建公开输入审查计划，保留 09:44 全量冻结闸门。
- 2026-10-21 09:40 +08:00：记录真实两边界失败、获授权的最小修复和原 12/1967 通过，提前冻结并保留部署限制。
- 2026-10-21 09:41 +08:00：仅补新接线说明及本计划引用；源/测试/fixture 不变，不重复测试。
