# B1：固定 b9 包的本机 Linux 增量、恢复与切换演练

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。所有记录与窗口使用 Asia/Shanghai（UTC+08:00）；不读取本机系统时区作为业务依据。本计划处理 2026-10-20 晚用户调整后的主线第 9 项，排在队列 0 后、事件契约冻结前。

## Purpose / Big Picture

用真实本机 PG15 证明：已有 schema4 Core 库可以先备份、在分离库恢复、用固定 b9 候选迁到 schema7、按原角色边界继续工作；最新撤销和 sent/uncertain 收据不会因恢复而回退。另证明三个业务服务、报告 timer、CHART_PYTHON 与 Hermes wrapper 在维护门和 writer 栅栏内一致切换，失败保持关闭。演练不表示 stage 或生产通过，更不解除授权条件。

## Progress

- [x] (2026-10-20 22:49 +08:00) 已完整阅读 28 前四节、29 授权原文、33 公共/主线及 B1 旧操作单、控制器、离线验证；文件和命令按源码核查。
- [x] (2026-10-20 22:49 +08:00) 明确三轨：固定 b9 的 schema1–7；另行 P1b schema8 本机兼容；真实 B/D 只获准 0005–0007。不得混包、不得改旧迁移。
- [ ] 本机 Docker/WSL 与 PG15 容器可用性、镜像身份和专属资源登记；当前仅知代理正在核查，尚无启动/测试成功证据。
- [ ] 合成 schema4 → dump → 新库 restore → 固定 b9 迁 schema7、owner/writer、容量、回滚的真实演练。
- [ ] stage 恢复副本专用撤销/收据重放 CLI 与真实 PG 正反例、幂等验证。
- [ ] 三 unit/timer、CHART_PYTHON、Hermes wrapper、维护门/fence、部分失败止损的 Linux 验证。
- [ ] 两份执行单已初稿，待实际工具参数与演练结果补齐；未核环节保持阻塞，不写 Go。
- [ ] root 审查、目标测试、提交/推送，汇总第一段报告通过与阻塞；执行 stage 另按 30 号条件授权。

## Surprises & Discoveries

旧操作单中 0.74GiB 是 10-18 只读观测。用户已说明磁盘清理完，不能继续把清理选择当待决；但没有新服务器观测，获准 B0 仍需核 ≥8GiB。固定候选 b9 只有迁移1–7，用户本机演练含0008不能解释成 B1 服务器迁8授权。

旧 `tools.core_incremental` 只有 backup/migrate/backfill，始终 `publication=false` 且保持停写。它没有开门/回滚子命令；旧 `restore-withdrawals` 硬 live，不能用于 stage。Native 原版 bare PATH 二进制、venv 完整性、systemd 有效配置、跨 exec fence 与恢复 proof 都没有 Linux 实证；28项替身绿不能消除这些门。

## Decision Log

2026-10-20 22:49 +08:00 / Codex：发布包固定 b9，操作工具可从本次工作分支单独审核、哈希绑定；不得把 P3/P1b 源码或0008装入 b9。所有未经真实演练的步骤在执行单标阻塞；没有实际 CLI 时不编造命令。schema7 的回滚须恢复 schema4 备份并重放最新撤销/收据，不能只把旧7dbc解释器接到schema7。

2026-10-20 22:49 +08:00 / Codex：30/31 号文件当前不存在，今晚不访问服务器。用户委托允许在条件满足时执行：B 要北京时间10-21 08:30以后、30明确 Go、先完成修改；D 只按31明确 Go 的工作日10:00–13:00窗口、写出后至少12小时，并遵守29第五节b。服务器操作异常停在原状态等大脑，只有SSH拒绝按10分钟间隔最多3次。

## Outcomes & Retrospective

当前仅交执行单/计划初稿；真实 Linux/PG 测试与完整开门/回滚接口尚未核准，B1仍 No-Go。测试、提交号与正式结论由 root 随演练追加，不沿用旧替身或预期当结果。今晚0服务器、0真实模型、0飞书、0合并到主干。

## Context and Orientation

复用 `tools/core_incremental.py` 的 authorize/execute 与分阶段回执；`core_incremental_files.py` 的逐文件hash、固定wrapper、manifest-last；`core_incremental_host.py` 的维护门、停写、fence；`core_incremental_pg.py` 的PG身份、prefix、权限与原文摘要；固定 b9 的 `tools/deploy_core.py` bundle/prepare/export_withdrawals/apply_withdrawals，以及 `tools/backfill_v4.py`。不能调用 freeze/install/publish/maintenance 代替增量，不重导SQLite/JSON，不改旧解释器退役、不改生产私有数据。

源码工作树为 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。发布候选 b9a89b6f84f7bebb640de080548010859aae630c，前包7dbc951eaffebd3d812169865eaefcde16a00ed9；候选manifest SHA256为49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c。凭据仅进受保护进程/0600文件，不入命令行、计划或回执。

## Plan of Work

先由 Linux 代理确认本机容器/独立PG，然后建立明确带任务标签的新合成源与恢复库，复现4→7及独立8轨。重放代理提供只允许获准恢复副本的入口，默认只检查，应用须显式quiesced与allowlist身份。root补小范围切换/开门/回滚控制器，分别验证正常、取消、中断、输入漂移。文档代理据真实接口补 B0–B8 与生产操作单。每片保留原始hash和安全计数，未完成处写明。

## Concrete Steps

本机命令与实际参数随脚本交付写入 `B1_stage_runbook.md` 本机演练段。现有控制器无副作用输入核验入口为：

    python -m tools.core_incremental --request <本次无密钥请求JSON>

真正执行某片之前，先看同一模块 `--help` 与精确提交，配置中的source/target/hash/角色/端口全部核对，不能复制合成approval充当30/31授权。目标测试可随里程碑执行；整库回归仅北京时间每小时00–15分开始，全队测试进程不超过4。root每40分钟以内提交/推送，未完成可wip。

## Validation and Acceptance

观察合成PG真实状态，而非只测返回JSON：源schema4原文/固定牌/撤销/Outbox计数与摘要一致；迁移1–4 checksum不变，新增5–7与b9文件一致；第二次回填各新增计数0；writer无DDL/ownership/继承且三个新表CRUD；恢复副本重放后撤销不复活、sent/uncertain不重发；重复重放无变化。恢复schema4后旧7dbc只读/合成业务可用；失败门保持关闭，三个服务与wrapper不能混用SHA。

B1已有脚本基线为80场景/48自检和Core/v4/Charts，无真实模型；明确复用固定候选版本，不能跑P3树结果冒充B1。B1危机支持涉及S01的程序热线模板，真实模型质量不是此次Linux演练的通过项。

## Idempotence and Recovery

每个演练/操作使用新的任务ID、输出文件和专属容器标签。仅可清理本次创建并核验的本机合成资源，不能删共享容器/volume或服务器旧文件/库。迁移没有down；重放按最新单调账本/收据执行。任何真实服务器动作异常不自行修后重试，保留维护/栅栏/回执；把当前状态交大脑。只有在委托D开门60分钟内的严重故障可按已审回滚单恢复，超过60分钟不得回滚丢新数据。

## Artifacts and Notes

执行单：`docs/v4/release/B1_stage_runbook.md`、`B1_prod_runbook.md`；本机证据由 `docs/v4/evidence/B1/2026-10-21-linux*` 与 `2026-10-21-replay*` 提供。旧A盘点与旧28项替身验证保留为历史；新证据不覆盖旧hash/旧计数。root日报、08:00四线汇总须先写B1通过与否、操作单是否就绪、剩余阻塞。

## Interfaces and Dependencies

外部控制器请求/approval/hash/proof契约仍以 `B1_incremental_runbook.md` 为基础。stage重放与开门/回滚接口尚在实现，定稿后补执行命令和源码hash，不推测可用选项。无新增第三方依赖；容器PG15镜像及已锁定Python依赖之外需要新依赖则列待决。B1包与工具版本分别记录。

## 修订记录

- 2026-10-20 22:49 +08:00：建立本机Linux/恢复/切换计划，复述最新授权与固定包边界；未提前填写成功测试。
