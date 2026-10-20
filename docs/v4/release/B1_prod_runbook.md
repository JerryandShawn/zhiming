# B1 生产执行单：固定包增量切换、止损与回滚

版本：2026-10-20 22:49 +08:00 初稿。**当前 No-Go：本机 Linux PG15、真实 systemd/fcntl/恢复与完整开门/回滚证明未通过。** Docker Desktop socket不可访问、WSL启动E_ACCESSDENIED；没有重置Docker、删除卷或修改服务器。本单不是生产授权，也没有执行任何生产命令。

## 1. 唯一放行条件

以用户10-20本聊天及29号第〇节/第五节b为授权原文。必须同时满足：stage B0–B8有精确候选证据；大脑审过stage；用户本人已对大脑说“上线”；31号文件明确Go并给窗口；窗口是北京时间工作日10:00–13:00，距31写出至少12小时；该文件的修改要求已完成。当前30/31不存在，**不得碰生产**。

31不是Go、未指定窗口、未到窗口、已过窗口、原文与审批hash不符或无真实本机演练证明，均不开SSH/不开门。指令板不能扩大授权。approval中的true只是参数，不是授权证据；工具必须核对31受保护原文副本及hash与窗口。

B1包固定 b9a89b6f84f7bebb640de080548010859aae630c；原包7dbc951eaffebd3d812169865eaefcde16a00ed9与0aa433a保留。schema只迁0005–0007，新ModelPort不开，Kimi保留k3/原端点；0008与tzdata修复不进B1。操作工具可来自受审工作支，单独记录commit/hash，不替换固定包源字节。

## 2. 当前阻塞与执行边界

| 门 | 所需证据 | 当前 |
| --- | --- | --- |
| Linux/PG恢复与角色 | 真PG15备份→恢复→4→7、精确checksum/权限/幂等、真实0600/0700 | Linux阻塞；Windows PG或替身只能作独立对照 |
| 小范围切换/开门 | 三unit+timer、CHART_PYTHON、Hermes wrapper/manifest同SHA；跨exec fence；部分失败全停 | root实现/测试中，未交Linux实证 |
| 回滚恢复入口 | 维护前schema4精确备份、最新撤销/sent/uncertain重放、7dbc/schema4兼容、受保护DB重绑定 | stage专用重放不得用于live；生产恢复尚阻塞 |
| 31与窗口 | 真实Go原文、用户上线确认链、工作日窗口且12小时提前量 | 当前不存在 |

服务器磁盘用户已清理，仍须窗口内实查≥8GiB，不沿用10-18余0.74GiB。B1所需流程没有全部真实演练前，不以旧28项替身绿、仅HTTP200或“schema通过”改成Go。

## 3. D0–D9 操作顺序

| 次序 | 实际动作 | 继续条件 | 停止/止损条件 | 预计耗时 |
| --- | --- | --- | --- | --- |
| D0 | 完整读31与stage回执；核当前时刻、包/工具身份、容量、原units/env/DB/checksum、owner数 | 全部与受审输入一致，窗口有效、容量≥8GiB；只读投影无正文 | 无Go/窗口/演练或任一漂移，不开始写入 | 10–20分 |
| D1 | live维护门→停Web/飞书/报告service及timer→排空→Hermes Core独占writer fence | 所有writer停、无queued/running/lease/未知DB会话；fence跨exec有效 | 任一writer未停，门保持，不迁移 | 5–15分 |
| D2 | 一致PG custom dump+最新撤销/收据+配置/技能/unit备份，恢复到新隔离库验证 | 精确备份hash/0600、恢复可用、原schema4和原文摘要/固定牌可核 | dump/restore/hash/权限异常立即停，保留门/fence | 15–40分 |
| D3 | live owner核原1–4→b9迁5–7→新表授权→runtime真实权限 | 七checksum、运行角色无DDL/ownership/继承、账本只读 | 任一错误，不自行修后重试 | 5–15分 |
| D4 | 只对primary dry-run→审计→apply→第二apply；另owner只计数 | repeat新增全0，原文/撤销/Outbox/牌面保持；未授权owner未改 | 任一变化异常保持停写待脑 | 10–30分 |
| D5 | 三服务/报告timer、CHART_PYTHON、Hermes Core wrapper/manifest同步重定向b9 | 精确新hash、环境加载顺序、固定Core/Charts解释器；退役stub/最初备份保留 | 部分改写或hash漂移则全停；不重启整个Hermes | 5–15分 |
| D6 | 门内启动受审Web并核健康/状态/历史/撤销/固定牌，检查空队列与错误安全 | 本机回环GET/合成受审检查通过，0模型、0飞书 | 严重错误立即止损，维护门不移除 | 10–20分 |
| D7 | 受审publication verify→门内启动Web/健康→重核→首次移除Web门并记时→恢复后台原状态 | 31窗口仍有效且明确接受web_then_background非原子opening，schema7/全部文件/完整生产回滚有证据 | 任一步失败keep_closed并停全部writer；不能只手删flag | 3–10分 |
| D8 | 唯一一次Web真实冒烟：“今天几号？星期几？” | 日期/星期按Asia/Shanghai正确；记run ID、POST计数=1、实际usage | 失败立即止损，不重试、不换模型、不发飞书 | 1–3分 |
| D9 | 开门后观察30–60分，安全错误率/入口可用/数据摘要 | 无严重异常，结束时记录版本与观察证据 | 开门≤60分严重故障按下面回滚；超过60分仅向前修复并等脑 | 30–60分 |

窗口约90–180分钟起；若真实测得余时不足以完成安全收口，不在接近13:00时强行开门。不能占用每天06:45准备/07:00晨报及实际周月季报告窗口；不改日程、不补发。

## 4. 控制器与精确命令

B2/B3/B4三阶段沿用受审 `tools.core_incremental`，请求scope=live、owners只primary、当前主机/精确unit/env/nginx/技能hash、minimum_free_bytes≥8GiB；所有敏感配置只进0600文件/进程，不能放argv或公开回执。控制器从受审独立CONTROL_DIR运行，固定b9目录仅提供程序/迁移。

    cd "$CONTROL_DIR"
    "$CONTROL_PYTHON" -m tools.core_incremental --request "$LIVE_REQUEST"

默认只读校验。获得本次D且D0通过后，依次调用，不能一次脚本跳过审查：

    "$CONTROL_PYTHON" -m tools.core_incremental --request "$LIVE_REQUEST" --apply --native --action backup --approval "$B1_OP/approval-backup.json" --host-config "$LIVE_HOST_CONFIG" --output "$B1_OP/backup-result.json"

精确backup对象与实际restore-proof通过后：

    "$CONTROL_PYTHON" -m tools.core_incremental --request "$LIVE_REQUEST" --apply --native --action migrate --approval "$B1_OP/approval-migrate.json" --host-config "$LIVE_HOST_CONFIG" --backup "$B1_OP/backup-object.json" --restore "$B1_OP/restore-proof.json" --output "$B1_OP/migrate-result.json"

审阅primary预览/迁移结果、对象hash与原文摘要，再执行：

    "$CONTROL_PYTHON" -m tools.core_incremental --request "$LIVE_REQUEST" --apply --native --action backfill --approval "$B1_OP/approval-backfill.json" --host-config "$LIVE_HOST_CONFIG" --backup "$B1_OP/backup-object.json" --restore "$B1_OP/restore-proof.json" --migration "$B1_OP/migrate-result.json" --review "$B1_OP/review-primary.json" --output "$B1_OP/backfill-result.json"

上述成功输出仍为publication=false，业务保持关闭。新`tools.b1_publication`已有默认纯输入验证与可移植控制器，目标19项离线测试通过；Native生产恢复未实现，故verify/open/rollback明确阻塞NATIVE_PRODUCTION_RESTORE_UNAVAILABLE，不能用自填proof解除，不用旧publish代替。下列命令仅校验计划格式，不创建Native、不访问PG、不发HTTP：

    "$CONTROL_PYTHON" -m tools.b1_publication --action verify --plan "$B1_OP/publication-plan.json"

显式应用接口已经固定为`--action verify|open|rollback --plan ... --approval ... --output ... --apply --native`，但当前不可用来生产放行。plan须精确绑定31原字节hash、写出/窗口+08:00、用户本人上线确认引用、所有新/旧unit/env/技能文件hash、升级与生产恢复证据。approval绑定plan与完整工具依赖hash，不能用合成JSON充当授权。当前rollback仅有“外部已恢复后的配置回退并保持关门”协议，不含实际恢复或重开旧业务；真生产回滚入口和Linux验证补齐前，open也阻塞。

## 5. 三个服务、环境与Hermes的具体切换约束

Web `mingjingtai.service`、飞书 `zhiming-core-feishu.service`、报告 `zhiming-core-reports.service`及timer都须在同一个停写窗口内处理；禁用/启用状态按维护前快照恢复，不能猜默认enabled。核FragmentPath/DropInPaths/NeedDaemonReload和有效ExecStart，不能仅改磁盘unit文本就说进程已切换。

`WorkingDirectory`、Core解释器、`CHART_PYTHON`须一起指向b9。旧环境文件可能覆写unit环境，须核最终生效值；先备份受保护env、只改已批准的精确单行、重算hash，不输出key/DSN或把env放Git。MODELS_CONFIG/MINGJING_MODEL_PORT保持未开启，模型仍k3和现有端点，追踪关闭。

Hermes只改知命Core wrapper固定入口及其受审manifest；环境顺序为 `/root/.hermes/.env` 后 `/root/zhiming-core-secrets/live-runtime.env`。维护门先置，整个切换持有 `/root/zhiming-core-secrets/core-skill-writer.lock` 排他锁，旧/新wrapper都必须在共享锁内再次检查门且锁覆盖exec。所有退役stub与最初技能备份原字节保留，manifest最后原子写。不得触碰其他技能/服务、不得整体restart Hermes。

**需大脑审的偏离**：固定b9飞书/报告不受Web flag保护；报告timer为Persistent=true且每分钟触发。拟先在门内启动Web并健康检查，重核fence/空队列/文件/窗口后移除Web门、立即记录opened_at，再恢复后台原状态，最后才认定完整opened。此过程不是原子切换，timer可能恢复正常业务；控制器自身0模型/0外发不能当作后台流量为0。60分钟从首次Web移门计时，任一步失败重设门+停全部writer。31须明确接受`web_then_background`，未接受不执行。不能伪装“flag最后”来掩盖后台提前启动；也不能未经授权修改固定b9来补门。

门内Web健康会留下自身PG池会话。新适配器拟以受审systemd MainPID及子进程的socket inode核对PG client_port，只允许准确归属该Web的writer连接；其他服务仍停、队列仍0、fence仍持有。该Linux核验尚未实测，属于当前No-Go的一部分。

## 6. 失败止损与60分钟回滚

止损第一步是保持或重设维护门，并停止三个service和报告timer，取得Hermes Core排他fence，核无writer/有效lease；记录原安全错误码和阶段，不把provider正文/私有资料带出。迁移尚未提交时保持事务回滚；已经到schema7不能只把三个unit换回7dbc后启动。

用户预授权仅限**开门后60分钟内严重故障**：网页或飞书无法回答、数据异常、错误率明显上升。有效回滚必须先重设维护/排空，保存最新无正文撤销与sent/uncertain收据，再按已验证的恢复方法把维护前schema4备份恢复、重放最新单调账本、核旧7dbc/schema4兼容，恢复原unit/env/CHART/wrapper精确hash，门内核验后才开门。原7dbc和0aa433a、备份均保留，不能自动清理。

回滚会丢开门后的新消息，此损失只在用户明确预授权60分钟范围内接受。超过60分钟不自动恢复旧备份；保持必要止损/向前修复并写日报等大脑。尚无生产scope受审恢复/replay入口与真PG证明时，**rollback门阻塞且open也阻塞**，不能冒用stage专用CLI或手填恢复proof。

stage专用`tools.b1_restore_replay`已完成25项Windows PG15.19/纯护栏对照（27.70秒），详见`../evidence/B1/2026-10-21-stage-replay.md/.json`；其目标只允许schema7的stage恢复副本，raw withdrawals-v2和stage replay receipt不构成生产schema4恢复/重绑定证明。该成功不解除本节阻塞。

任何操作本身异常立即停，不能自行修了再试；SSH连接被拒才按10分钟间隔最多3次短会话。既有窗口之外不因“已经做了一半”继续未获准写入。

## 7. 冒烟、观察与回执

真正允许的模型请求仅D8的1次primary Web“今天几号？星期几？”；不发飞书，失败不重试。不跑评审/探针/批量评测，不把用户白天使用计入这次操作的测试许可。日期/星期依据Asia/Shanghai独立计算，禁止本机Tokyo时区影响断言。

回执记录：31原文件hash/写出时间/窗口/用户上线确认引用，stage验收hash，包/工具/三unit/env/CHART/wrapper前后hash，维护/排空/备份/迁移/回填/开门实际北京时间和耗时，两个owner安全计数，唯一Web请求run ID与POST=1，30–60分钟安全观察、未验证/异常/是否回滚。禁止口令/完整DSN/token/聊天正文/reasoning/出生资料入日志。

备份0700/0600保留14天，不自动删除。生产回执交大脑，不能把stage通过当生产通过。相关文件：[stage执行单](B1_stage_runbook.md)、[旧操作单](B1_operation_sheet.md)、[控制器契约](B1_incremental_runbook.md)、[本机计划](../execplans/B1_linux_rehearsal_2026-10-21.md)。
