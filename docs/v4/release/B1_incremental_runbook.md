# B1 已有 Core PG 增量控制器：离线实现与执行边界

本轮实现独立 `tools/core_incremental*.py`，不调用旧 `freeze/install/publish/maintenance/restore-withdrawals` 作为增量入口，不重导SQLite/JSON，不重新启用旧解释器。用户已裁定 B1 固定 b9a89b6，tzdata随B2；容量明天决定，今晚只有本地替身测试，没有任何服务器访问或真实模型/消息。

这是外部操作控制器，不属于固定 b9 发布包。它自己的全部 `core_incremental*.py` 文件形成控制器哈希，授权文件同时绑定请求和控制器哈希。新增控制器不意味着可以把当前 P3 源码打进 b9 包。实际服务器运行、SQL语法、Linux文件权限与故障恢复仍须在获准的合成环境核验；当前不得据此宣布 stage/live 可执行。

## 已实现的可观察流程

默认命令只读请求JSON并校验，完全不创建主机适配器：

    python -m tools.core_incremental --request <无密钥请求JSON>

实际 apply 需额外显式选择 native、完整审批/主机配置和独立输出文件。以下仅接口模板，未获准，不能今晚运行：

    python -m tools.core_incremental --request <请求JSON> --apply --native --action backup --approval <0600审批JSON> --host-config <0600主机配置JSON> --output <新0600回执JSON>

控制器没有SSH后端，不接受任意shell命令；Native只在审批指定的本机 Linux/root/hostname 身份下运行。迁移与运行DSN只取进程变量 `CORE_INCREMENTAL_OWNER_DSN`、`CORE_INCREMENTAL_WRITER_DSN`，不进入argv、请求文件或公开错误。主机配置只含非密钥文件路径哈希、nginx哈希；不source环境文件。stage只允许对应stage库/独立维护flag/单位，不修改live Hermes技能。

固定输入：b9a89b6f84f7bebb640de080548010859aae630c；旧入口7dbc951eaffebd3d812169865eaefcde16a00ed9。按原bundle算法从本机Git b9的636个原始blob独立重算 `__release_manifest__.json`，SHA256固定为 `49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。若服务器包manifest不同，停止调查，不改常量迁就未知输入。逐文件hash、意外源码、迁移1..7以及schema4前缀均需匹配。

| action | 真实实现的动作 | 退出后状态 |
| --- | --- | --- |
| backup | 核代码/配置/容量→维护flag→停止全部受审writer→排他fence→真实PG只读身份/权限/队列/全表内容摘要→custom dump及无正文撤销旁账→重核摘要、文件0600/hash | `quiesced_backup_only`，无迁移/回填/业务恢复。需要在独立新库演练这份精确备份 |
| migrate | 相同停写护栏；核精确backup及已批准恢复proof哈希→schema4前缀→候选代码原生迁0005–7及新表授权→实际runtime权限/schema7复核→仅dry-run各获准owner | `quiesced_schema7_review_required`，输出迁移前后摘要和每owner预览hash；没有apply回填/切服务 |
| backfill | 审批绑定迁移回执hash、未改变的schema7状态及全部owner预览hash→逐owner重做dry-run核hash→apply→第二次apply零新增→固定unit/必要的Hermes wrapper重定向→仍停写 | `quiesced_upgraded`，`publication=false`。没有开门、启动服务、模型、渠道或旧代码回切 |

每一次退出和异常，包括进入fence中途失败，都尝试保持维护和全部writer停止；主机身份/源输入在任何写之前失败时不新改主机。停止命令逐writer尽力执行，不因首项失败跳过其余。原始异常正文/外部命令stdout/stderr不公开。备份、迁移开始/提交、retarget回执留在受保护 operation 目录。进程崩溃/receipt输出失败不自动重试；schema7已提交后不再假装schema4，须按持久证据审查向前修复。

## 请求与审批契约

请求schema为 `b1-incremental-request-v1`，字段为 operation_id、scope(stage/live)、hostname、target、previous、manifest_sha256、controller_sha256、owners精确列表、minimum_free_bytes、unit_sha256、skill_manifest_sha256及host_config_sha256。live writer集合固定Web、飞书、报告service及timer；历史stage固定核A所查的`mingjingtai-stage.service`和`zhiming-core-stage.service`，已确认不存在时以`absent`明确记录。合成Web新库/新服务另行初始化部署，不混入历史stage升级；历史stage元数据配置使用新建待授权的`stage-b1-upgrade-runtime.env`，不能复用合成Web或live配置。没有默认全owner、全unit或通配服务。

审批schema为 `b1-incremental-approval-v1`，含operation_id、scope、request_sha256、controller_sha256、带时区expires_at、quiesced_upgrade=true；resume_business/model_calls/channel_sends均须为false。migrate另需restore_sha256；backfill另需migration_sha256及backfill_review_sha256。审批应由获准操作人在用户具体授权范围内准备；JSON不是密码或数字签名，不能把自己填写布尔值当作外部验收。

三阶段沿用同一个operation_id和精确backup。`--backup`文件应为backup阶段回执内的`backup`对象，不能把外层状态回执当backup；`--migration`是migrate完整回执，`--review`是其中的`review`对象。migrate命令增加`--backup <backup对象JSON> --restore <恢复proofJSON>`；backfill增加这两项及`--migration <迁移回执JSON> --review <owner预览hash映射JSON>`。每步使用新的输出路径，不能覆盖已有回执。阶段中断不自动重跑，先审operation目录持久证据和实际schema。

哈希使用本工具`digest`：UTF-8、JSON按key排序、紧凑分隔符、拒绝NaN；对象hash与原始文件字节hash用途不同。请求中的`host_config_sha256`、审批中的`request_sha256/restore_sha256/migration_sha256/backfill_review_sha256`均为对象hash；release/unit/环境/nginx/技能文件为原始字节SHA256。`controller_sha256`为所有`tools/core_incremental*.py`文件名到原始SHA256映射的对象hash。备份中的dump/withdrawals为原始文件hash，不能换成JSON重序列化hash。

host-config的`env_files_sha256`必须正好覆盖上述scope要求的环境文件；live另含`nginx_sha256`，拒绝其余字段。审批绑定host-config对象hash后，任何环境文件、unit、技能或nginx漂移均停止。保护配置和审批文件用0600；DSN只存在受保护的进程环境。owner清单必须来自授权盘点；回执只保留owner hash和计数，不能复制正文作为核验样例。

restore proof为 `b1-isolated-restore-proof-v1`，绑定精确backup对象hash、候选/manifest、隔离目标（stage为`zhiming_core_b1_restore`；live为另待D/E授权的`zhiming_core_live_b1_restore`）、schema7完整checksum，以及实际pg_restore、最新撤销重放、sent/uncertain保护、runtime权限和零模型/外发结果。恢复目标必须在实际授权中明确创建。proof的生成与真实PG演练入口仍需另审，不能捏造证明解锁本控制器。

源dump为schema4，恢复库先核原前缀/内容，再由获准角色向前迁7和重授、重放最新无正文撤销/收据、只读核验；不直接用b9的initialize=False把schema4验成7。Native不会创建/清空/替换数据库，也不会执行自动pg_restore。

Native使用loopback5432、PG15、同库不同owner/writer；实际连接身份在业务读取前核实。运行角色无DDL/角色成员/业务表ownership，两个迁移账本只读；既有业务/checkpoint CRUD和新三表CRUD均核。queue/running/有效租约为0，拒绝其他数据库客户端。内容摘要在PG端聚合后仅返回hash，使用5秒statement timeout；大库超时将拒绝，不把未完成的摘要当通过。

## Hermes 固定入口的专门方案

live还必须取得 `/root/zhiming-core-secrets/core-skill-writer.lock` 排他锁，维护flag先置位，直到所有迁移、回填和重定向完成才释放。旧固定wrapper必须逐字匹配已审7dbc模板，技能manifest/全部文件/hash、未知Python文件、退役stub和原始技能备份都检查；任一漂移停止。这里只验证已审入口/明确unit，不能证明任意root或绕过应用锁的手写SQL不存在；这类写入口必须在窗口前盘点、停用并通过PG会话检查。

重定向在fence内先保存原unit、技能原文件及原manifest，再把三个服务的固定release路径改为b9，timer保持受审语义；wrapper使用b9 Core解释器及固定release，环境加载顺序保持 `/root/.hermes/.env` 后 `live-runtime.env`。退役stub保持原字节，最初的Hermes技能备份既不覆盖也不删除。不执行整体Hermes restart。

最后原子写新 `core3-hermes-skill-incremental-v1` manifest，绑定previous/new SHA、旧manifest hash、b9 source manifest、所有新文件hash及原始退役备份引用。旧deploy工具的 `verify_hermes_skill/publish` 不支持此新manifest，不能混用。当前不承诺运行中的Hermes指令缓存已刷新；须在合成环境证明下一次CLI执行使用固定新wrapper、旧入口仍拒绝、锁能跨exec覆盖执行，之后才能另审生产。文件写入中断时维护门与writer仍关闭，不能启动旧schema4包。

## 验证及剩余门

本地控制器测试覆盖真实替身状态改变，Native测试使用注入的命令/PG/fence和临时文件系统；subprocess、网络、系统exec均禁止逃逸。Windows不能证明POSIX0600，Native测试对此显式使用合成权限模型，不把它算Linux权限实测。新测试只运行本线文件；旧incremental_acceptance历史测试不修改。

本轮28/28离线检查通过，逐命令、源码hash、控制器hash、覆盖/未覆盖矩阵见[`B1_incremental_validation.md`](B1_incremental_validation.md)。这不替代真实隔离PG或B1验收，也没有改变固定b9发布包。

待补且阻断实际执行：Linux/真实隔离PG的SQL与权限验证；已运行7dbc实际wrapper模板/退役backup匹配；多进程CLI fence和部分retarget故障演练；精确备份的restore proof生产入口；unit drop-in/有效启动配置与出站隔离核验；容量整改及B授权；生产另行D/E授权。今晚不得借实现工具的授权执行这些远端操作。源码和文档交root审查提交，未获阶段验收前不报B1工具生产就绪。
