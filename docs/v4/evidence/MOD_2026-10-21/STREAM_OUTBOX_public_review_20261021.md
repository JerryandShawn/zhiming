# MOD 旧流式公开输入审查回执

- 分支 / 最后提交：归属 `v4/mod-organize`；root 独占 Git，本子任务没有提交，PR #10 保持草稿。
- ExecPlan：`docs/v4/execplans/MOD_stream_outbox_public_review_20261021.md`。

## 完成了什么

12 项独立小矩阵验证完整 core3、公开 Clock 与两个 freshness 边界，未重复上一轮 150 项历史验收。
首测 2 failed/10 passed/0.22s：payload 明确声明另一 subject，旧 core3 分支仍允许领取和发送。
已保存原失败与七源 SHA；没有把它藏进未完成清单来称回归绿色。

root 针对真实缺口明确授权后，仅在新模块 freshness.py 的 core3 分支加主体一致性判断。
完整 core3 的展示校验、run_id、依赖、来源 epoch、两次 freshness 和 unknown/CAS/租约规则均未改变。
原 12 语义真值不变，Ruff 仅整理 import。修后 12 passed/0.12s；两 P9 兼容套件 1967 passed/11.80s。

## 评测分数

修前 2/12 失败；修后 12/12 通过。兼容套件 1967/1967 通过，包含旧 1955 项和新 12 项。
09:39:19–09:39:32 北京时间的兼容观测前后七产品和完整套件测试/样例 SHA 一致。
本轮没有重测覆盖，不能把上一份七文件覆盖报告当作此源码哈希下的当前分数；真实模型调用为 0。

## 改了哪些关键文件

唯一产品改动：`mingjing_core/adapters/channels/stream_outbox_v2/freshness.py` core3 分支，
SHA-256 `85c509b6343d7e72d46fad2f35133e54816d9aa399611fcab47c791ba617d38f`。
新增唯一测试 `tests/v4/p9_v2/test_public_inputs_review_acceptance_mod.py`、本计划和新失败/验证材料。
新接线说明：`docs/v4/integration/mod/STREAM_OUTBOX_core3_subject_20261021.md`。
原产品调用方 Hermes、旧 tests/gold、前轮 150 项验收均未修改。

## 数据库迁移与回滚方式

无迁移，无运行态写入，输入全部虚构。产品校验不能回滚为允许明确 foreign subject 的旧行为；
主线如有历史缺失主体的记录，应权威补投影或拒绝，不能由当前主体猜填。

## 偏离设计的地方

无。core3 与 core4 共用 subject 隔离不变量；采用 core4 既有的 `validated_subject_mismatch` 原因码。

## 未验证 / 已知风险

只有合成反例，没有观察生产泄漏，也没有证明真实 PG/路由授权/飞书隔离。
trusted host 的投影不能自证实际查询了当前来源；metadata 指纹仍不是签名。
Clock 倒退缺少历史观察字段，本轮只记录主线 Clock 可靠性要求，不擅自添加新时间政策。
没有网络、模型、PG、通知、业务或运行态写入；没有读 Q5 B、校准 75 条正文；CI/全量由 root 后续负责。

## 需要用户或大脑决定的问题

无。09:44 起保持所有产品/测试/fixture 不变，直到 root 明确通知全量结束。

## 建议后续

在合法窗口重新测该七产品的 scoped branch 覆盖；以真实隔离 PG 验证完整 core3 来源主体投影。

首失败 JSON SHA-256：`25ec73577731c3ff91bcc363b0aebed73ff41e1b260834186a61a168c192a220`。
修后验证 JSON SHA-256：`d5f07884643997e3b72860fbad8f5234a8aa247d847ef06be0632a9c1ade512d`。
