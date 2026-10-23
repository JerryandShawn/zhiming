# MOD 旧消息桥独立边界阶段回执

- 分支 / 最后提交：工作范围 v4/mod-organize；提交及 PR 由 root 管理，本验证者未操作或查询 Git。
- ExecPlan：[MOD_legacy_bridge_boundary_20261021.md](../../execplans/MOD_legacy_bridge_boundary_20261021.md)
- 回执时间：`2026-10-21T11:14:40.145984+08:00`，Asia/Shanghai。

## 完成了什么

- 原 15 冻结真值未改；首测 1 failed / 14 passed 原始 stdout、失败 trace 和旧源码 hash 保留。
- root 最小严格标量修复后，原 15 项 15/15 通过 0.14 秒，LB08 拒绝而 LB15 缺省 revision 兼容保持。
- 两套 organize_supplement/organize_supplement_v2 必要兼容 529/529 通过，实际包含另一独立 5 项。
- 仅对 supplement_v2 九产品做一次 coverage；32/33 运行快照各自无漂移，新旧矩阵和全部原断言不动。
- 新 Python 已有 Ruff/格式/AST 检查通过；首测后原测试/helper字节未改，本验证者未修改产品或格式化既有文件。

## 评测分数

原目标修后 15/15；限定兼容 529/529（2.11 秒，插桩时间）。本轮未跑模型评测，真实模型请求 0。
覆盖：九文件行 554/603=91.8740%，分支 151/200=75.5000%，综合 705/803=87.7958%；旧桥行/分支均 100%。
这不是整 PR/项目覆盖，未声称全九文件综合达到 90%。

## 改了哪些关键文件

本验证者新增独立 test/helper、显式合成 fixture、first/postfix/限定覆盖证据、计划与新接线补充；旧测试/真值无改动。
产品修复由 root 实施，仅 legacy_bridge 的 raw revision/at_ms strict guard。本验证者没有修改产品。

- [首失败证据](LEGACY_BRIDGE_independent_first_20261021.json)，SHA `6bb2395267b4462f8657fae8a49f0d59490ca18cf0baa6a09af75674f3661adc`。
- [修后证据](LEGACY_BRIDGE_independent_postfix_20261021.json)，SHA `ec7ccd38ba153e6d0b0cd63b7bf0eb56406ac57634284fa6fca73c29e7844e7e`。
- [限定兼容/覆盖](LEGACY_BRIDGE_compatibility_coverage_20261021.json)，SHA `49419da399476a6cc28ee9f12360014aa24d2754400744034a24880eb672abda`。
- [新增接线补充](../../integration/mod/LEGACY_BRIDGE_boundary_20261021.md)。

## 数据库迁移与回滚方式

无数据库迁移、删除或真实写入；本验证者不执行 Git 回滚。root 管理源码提交，原失败历史及旧摘要不覆盖。

## 偏离设计的地方

无真值降低或范围扩展。LB08 不发明新错误码；root 复用固定 legacy_message_evidence_changed。
同类标量漏洞通过通用 exact-int 门禁处理，缺失 revision=1、匹配 revision=2 和整数 epoch 0 正例保持。

## 未验证 / 已知风险

真实 PG 事务、用户身份/点击、实际 apply/undo、CI、部署和负整数时间并未由本轮验证。
九产品仍有覆盖残余，报告给出逐行/分支明细；纯内存转换通过不能替代来源当前授权。

## 需要用户或大脑决定的问题

本轮无新增产品决定。后续是否扩展残余公开拒绝路径由 root 排期，不需夜间等待用户。

## 建议后续

主线接线继续事务内复核 owner/subject、来源修订/撤回/无痕、审阅及敏感同意，持久化稳定 operation 和逆操作账本。
保留首失败→root 修复→修后通过的证据链；本轮冻结，不自行扩大覆盖或重跑。
