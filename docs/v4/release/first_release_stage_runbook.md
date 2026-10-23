# 核心首发 stage 执行草案（B0–B8）

2026-10-24 00:01，北京时间；00:36补充本机同次升级基础。**No-Go / 草案：尚不能照本单完成部署。** 工具观察基线为`3ee8def`，最终首发候选尚未冻结；该提交号不是已验收的发布包。当前没有正式首发增量apply、Linux/生产新库恢复、回填、切换或开门入口；新增本机恢复及可选升级仅用于隔离演练。本单没有授权或执行服务器、模型或飞书动作。

本单取代首发范围内旧B1执行建议，不改写旧证据。旧授权B/D已取消；stage和生产分别需要用户对最终SHA、对象、窗口、动作与止损范围的新授权。大脑复核或本文件存在均不能代替该授权。当前不执行任何SSH、建库、备份、服务或网络动作。

## 1. 候选与安全边界

首发按当前`core-only-1-8-v1`契约覆盖P1/P1b/P2/P3、旧网页兼容和现有文字飞书入口；P4/P6及新前端不在此单。当前要求迁移0001–0008精确连续且checksum不变。P5若达到就绪门并纳入候选，须另审含0009的profile、关系/routine清单、恢复工具及本单，不能以忽略0009绕过现契约。

最终审核输入至少包括：精确Git候选SHA、规范Git blob发布manifest原始SHA、artifact SHA、迁移八项hash、`requirements-core.lock`、`requirements-charts.lock`、`k3-tokenizer.lock.json`、模型配置及依赖工具commit/hash。最终候选或任一运行源码变化后，已有候选脚本/质量/恢复证据须重新判断绑定关系，不拼凑不同来源的通过报告。

这是已有Core PG的增量路径：不重跑旧SQLite/JSON导入，不使用`deploy_core freeze/install/publish`迁移已有库，不使用硬编码live的`restore-withdrawals`。旧B1控制器、proof及Linux SQL drill仍固定b9、迁移1–7；它们的apply命令不能换个SHA直接用于本单，也不能把旧授权带过来。

0008中央额度账本独立于业务时间和恢复点：不回退usage/attempt/batch/stop，不清空或provision账户来通过启动门，不复用生产凭据或伪造account、ledger identity及实际PG location。若账本位置随恢复库变化、备份包含旧账本，必须有另审的保全与重绑定方案；目前没有该入口，届时停止。

所有故障保持当前维护/停写状态，保留私有产物与安全错误码，交大脑复核；不自行修好重试、不覆盖或删除旧库/容器卷/备份。时间均为Asia/Shanghai，测试不能依赖机器时区。本文所有耗时是排期估计，不是测得RTO。

## 2. 必须解除的门（当前全部未放行）

| 门 | 当前事实与缺口 | 放行所需 |
| --- | --- | --- |
| 候选身份 | 最终候选、manifest、artifact及外部审核pin待冻结 | 同一候选的明确审核、来源与必要评测；不能手填admissible |
| 实际Linux运行时 | 现有Windows PG定向证据只证明相应逻辑；Linux Core/Charts/K3未整体验证 | Python3.11双环境、锁依赖/导入来源、真实文件权限、官方K3本地小文件及网络隔离 |
| 增量与恢复 | 正式首发入口目前仅validate/可选只读ACL；本机可恢复并显式升级，尚无正式恢复实现 | 新库真实备份恢复→精确1–8→最新撤销/送达收据双重放→重复零变化→checkpoint与权限证据 |
| 停写与切换 | 最终Web/飞书/报告+timer、Hermes wrapper及维护/锁尚未联合演练 | 实际Linux跨exec writer栅栏、部分失败保持关门、所有入口同源 |
| 当前环境及授权 | 未做新的服务器盘点；容量、旧schema/服务状态不能沿用历史值 | 用户新的stage授权，明确新对象/窗口；获准后只读B0复核一致 |

关系/函数/ACL校验通过不代表数据已恢复、运行时已受信、中央账本已合法迁移或渠道已验收；本单不将任一门标为“已解除”。

## 3. 现有可运行的校验命令

以下仅描述已有接口，**本轮没有运行**。所有变量须先由审核输入绑定为绝对路径；不从任意env文件source，不在argv放口令、DSN、token或正文。`FR_CONTROL_DIR`是含已审工具的目录，`FR_CONTROL_PYTHON`是其固定解释器。未有正式候选和pin时先停，不能用合成测试pin代替。

```bash
cd "$FR_CONTROL_DIR"
"$FR_CONTROL_PYTHON" -m tools.first_release_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT"
```

默认只有文件/契约校验，PG连接数0、mutations=0。外部pin格式为`first-release-pin-v1`，契约为`first-release-restore-contract-v1`；字段以[源码契约](../../../tools/first_release_contracts.py)为准，不能多加通过布尔位。正式源码路径固定`/root/zhiming-core-releases/<最终SHA>`；本机模式须显式`local_drill=true`，且源码位于当前工作目录的`private/first-release-<operation随机标识>/<SHA>`。本机模式的成功不是Linux放行。

正式允许的新恢复目标仅`zhiming_core_first_restore`及对应`_owner`/`_writer`；本机仅`fr_restore_<operation随机标识>`。该目标不是原stage库，也不是可用于任意数据库的模板。当前工具不创建这些对象，目标不存在时不能自动创建。

未来恢复apply还须证明目标为空且属于本次操作。stage完成后应保留恢复副本；同机生产若遇到同名已占用目标，先停下另审独立目标/契约，不删除或覆盖stage副本来腾位置。

当且仅当本机测试范围或新的stage授权允许、且独立恢复库已通过另审步骤建立后，可增加：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --check-acl
```

只由受保护加载器注入`FIRST_RELEASE_OWNER_DSN`与`FIRST_RELEASE_WRITER_DSN`；角色/库/loopback/端口必须一致，实际进程及显式环境均不得夹带PG隐式路由变量。工具各开一次只读事务，先固定并核验`search_path=pg_catalog`，检查真实PG15身份、精确关系/routine、额度表/列/序列权限、两个迁移账本只读及checkpoint DML；不修授权、不迁移、不重放。该入口不接受原stage/live DSN，不能拿它直接扫描业务库。

正常输出始终`runtime_verified=false`、`linux_attestation=false`、`native_restore_completed=false`、`publication=false`，没有`admissible=true`。外部pin被视为可信审核输入，但工具不认证审核人、pin保护模式、真实Git tree归属或审核新鲜度，这些仍由发布审查负责。`--apply`、`--native`及`--action migrate`均不是此入口的命令。

本机最终干净checkout的打包接口已存在；冻结之后才可按审核路径运行，打包不等于部署：

```bash
"$FR_CONTROL_PYTHON" tools/deploy_core.py bundle \
  --commit "$FR_SHA" --release-dir "/root/zhiming-core-releases/$FR_SHA" \
  --source "$FR_CLEAN_CHECKOUT" --artifact "$FR_LOCAL_ARTIFACT"
```

构建要求checkout HEAD与SHA一致、工作树干净。不得将测试库、凭据、备份、真实正文或未跟踪运行目录打进发布包。

## 4. B0–B8：动作、继续与停止条件

### 本机新入口（不能替代B3/B7）

`tools.first_release_local_restore`已提供本机原始prefix恢复基础。外部同源审核dump-pin为`first-release-local-dump-pin-v1`，绑定候选/manifest、custom dump及PG15 pg_restore原始hash、源迁移前缀；只接受1–7，实际验证4或7。示例为已存在接口，不表示现在授权服务器执行：

```bash
cd "$FR_CONTROL_DIR"
"$FR_CONTROL_PYTHON" -m tools.first_release_local_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --dump-pin "$FR_LOCAL_DUMP_PIN" \
  --dump "$FR_LOCAL_BACKUP_DUMP" --pg-restore "$FR_LOCAL_PG_RESTORE"
```

默认只读文件、0PG/0子进程；显式`--apply-local`才创建本次随机新库/新owner和writer并实际恢复。必须local_drill=true，dump固定在本次operation目录的backup.dump，管理DSN仅同一loopback 55480/55481的postgres/core_test_main控制库。任何既有目标库或任一角色均拒绝；失败保留新对象，再调用拒绝接管，不清理重跑。应用前实际TOC检查拒绝中央额度表，即使dump-pin谎称prefix7也不复制0008。

新public初始化仅在本次新库/新owner匹配、public为空且原owner为pg_database_owner时进行，不放宽NOINHERIT或writer权限。角色DDL只提交客户端生成的SCRAM verifier，口令和verifier均不进回执。实际pg_restore由新owner执行no-owner/no-acl/exit-on-error/single-transaction/no-password；默认随后只核原prefix和owner。

同一命令显式增加`--apply-local --upgrade-local`，才在该调用持锁新建且恢复的目标继续：再次核候选SQL和历史、一个事务前向至8、独立autocommit阶段checkpoint setup、复用最小授权、两角色精确只读ACL。正常总连接7，默认路径仍4；没有采用现成库的单独入口。0008四表必须实际为空，非空立即停止并保留，不清表或provision；空表不代表中央账本合法保全/重绑定。任一阶段失败保留其已提交现场，不修权限重试；不重放撤销/收据。成功仍保持正式native_restore_completed、linux_attestation、publication为false。本机新升级窄链11/11及原恢复证据见原ExecPlan，不新增证据副本。B3/B7所需正式全链仍缺失。

**B7的新库恢复证明必须在B3修改已有stage库之前完成。** 表中缺失入口不是待猜命令，不能用旧B1 apply或手工SQL补过门。只要必要入口缺失，停在本地准备阶段。

| 步骤 | 动作与当前入口 | 继续条件 | 停止条件 | 预计耗时 |
| --- | --- | --- | --- | --- |
| B0 | 新授权后只读盘点主机、PG15/实际schema前缀、角色、服务/反代、队列、磁盘和备份；命令范围见下文 | 目标、旧包、schema/checksum、owner范围及容量与审核输入一致；所有目标名称明确 | 无新授权、环境漂移、低于受审容量预算、未知writer/旧任务 | 10–20分 |
| B1 | 本机冻结最终候选并规范打包；§3 validate；受审渠道传包/准备双环境的首发入口待补 | manifest/三锁/1–8一致；实际Linux Core、Charts、K3来源与权限均验过 | 依赖/额外文件/解释器不符；最终包未定；只有Windows或元数据证据 | 30–60分，下载另计 |
| B2 | 保持stage停写，取得stage专属writer栅栏，精确备份与导出最新无正文旁账；首发控制器缺失 | 队列/lease/其他写会话为0；dump、原schema、状态摘要、撤销/收据及配置可绑定 | 无停写证据、来源读取依赖源库尚无的表、备份或导出失败 | 15–30分 |
| B3 | B7已通过后才允许已有库前向迁至8、checkpoint setup及最小授权；首发apply入口缺失 | 原checksum合法连续前缀，目标八项精确一致；新恢复证据同源 | 任何迁移/身份/ACL异常；禁止改历史迁移或补多余DELETE | 10–20分 |
| B4 | 对明确获准owner dry-run→审核→apply→repeat；首发回填控制器缺失 | 重复新增全部0；原文/来源/牌面/撤销/收据不变；未获准owner只核计数 | repeat变化、丢正文或固定牌、owner越界、收据回退 | 10–40分 |
| B5 | 最终候选同源的必要脚本与定向回归；只用可丢弃验收库、替身传输；不在实际stage历史库跑测试 | 首发脚本/集成证据已满足当前门，无未解释失败/跳过；来源一致 | 假目标代替v4、旧报告凑绿、测试连业务库、触发真实供应商/消息 | 30–60分，按规模修正 |
| B6 | 独立合成Web库/owner/writer/目录/端口/unit与实际出站封锁；首发装配/启动资产待补 | Agent实际启用且替身装配受审；loopback PG阳性/同cgroup出站阴性有对照；历史与记忆回执等行为通过 | 借live env/目录/中央身份，关闭Agent只验旧health，网络封锁未实证或有待恢复真实任务 | 20–45分 |
| B7 | B2精确dump恢复到新allowlist库→核原前缀→前向1–8→最新撤销/收据重放两次→§3只读ACL；实际恢复/replay入口缺失 | 非空deleted_draws墓碑可再导出、owner隔离；sent/uncertain不重发；checkpoint清除；第二遍无变化；中央账本不回退 | 复用旧b9恢复、覆盖stage/live、过期旁账、中央账户重建、任一状态/权限/提交后checkpoint异常 | 30–60分起 |
| B8 | 一份stage回执，绑定候选/工具/配置与每步证据和实际耗时，交大脑审核 | 所有必要门真实完成，停止状态和未验证项明确 | 输入或步骤缺失仍写stage accepted；自动进入生产 | 10–20分 |

B0获准后的现有只读命令可包括`hostname`、`date --iso-8601=seconds`、`df -B1 --output=avail /`、`ss -lnt`及对**授权所列精确stage units**的`systemctl show`（Id/ActiveState/UnitFileState/FragmentPath/DropInPaths/NeedDaemonReload）。不打印Environment、完整DSN、私钥、正文；PG安全投影工具/当前参数未核准时停止，不临时拼接含口令命令。

容量以本次盘点和实测数据库/备份/双环境/恢复副本占用加余量计算；不能因历史磁盘已清理就认定充足。首次整体准备暂按3–5小时估计，缺失实现、审核和依赖等待另计；不能承诺维护时间或RTO。

## 5. B6/B7还缺的具体内容

独立合成环境需分别批准测试DDL库、Web库与恢复库的精确新名称和角色。当前validator只支持恢复目标，不存在通用`--stage`部署参数。旧[B6资产](B1_B6_stage_assets.md)固定b9、schema7及旧启动逻辑，只能参考隔离方法，不能原样安装后声称P3已通过。

Agent启动还要求明确的`MINGJING_AGENT_ENABLED=true`、至少三条运行容量、同源模型registry、已有中央account/ledger identity/location及已验`K3_TOKENIZER_DIR`。当前生产装配并非一个现成stage ScriptedProvider启动器；必须补受审离线装配，不能塞假API key或发真实请求来证明启动。P6独立评审不随此profile开启。

恢复证明须观察实际pg_restore及空目标、备份源前缀、全部owner、最新撤销/墓碑/delivery收据、checkpoint及两次状态摘要，不接受手填字段。源前缀4/7/8如何安全读取旁账、旧包/旧schema回退兼容、中央账本保全与重绑定、提交后checkpoint或回执写入失败的停留状态，均要先实现并本机Linux演练。

当前精确ACL仅支持已审24张Core表、4张checkpoint表、0008单sequence和0007受审invoker触发函数；额外关系/规则/例程拒绝。新组件有真实需要时先变更审核profile与测试，不能临场宽授权。

## 6. 失败与回执

异常立刻停止，保留stage维护门/栅栏与私有产物；不自动删除新库再跑，不覆盖原stage，不启动旧代码配不兼容schema。**仅开门前可按另审并已演练的回滚方案恢复；开门后只关门止损、停writer、保存现场，等待审核的向前修复。** 本单不包含任何可执行rollback命令。

B8记录实际北京时间、候选/工具/manifest/三锁、PG版本/角色/迁移安全投影、备份与最新旁账hash、两次回填/重放计数、ACL/网络/DOM行为、未完成项与停止状态。只引用现有证据索引，不复制多套证据。真实模型、飞书或外部消息默认0；任何真实冒烟须另有精确授权。

相关来源：[恢复ExecPlan](../execplans/first_release_recovery_20261023.md)、[校验入口](../../../tools/first_release_restore.py)、[精确ACL](../../../tools/first_release_acl.py)、[生产草案](first_release_prod_runbook.md)。旧[B1 stage单](B1_stage_runbook.md)是历史范围，不能授予本次权限。
