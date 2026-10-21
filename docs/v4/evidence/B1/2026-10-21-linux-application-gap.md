# B1 Linux应用演练：代码差额与最小接口

北京时间2026-10-21 08:44，只读审计基准c7d760addc63ea9c8a12d15d08123b32f6e17238。指令板v2和30号结论No-Go；本次没有运行pytest、Docker/WSL命令、PG写操作、服务器连接、模型或飞书。没有第三次环境尝试，也没有创建linux-actual.json或手填restore-proof。

## 结论

即使Docker恢复，现`tools.b1_linux_drill --apply`成功也只能证明PG迁移切片，仍不能完成指令板第3项的primary应用回填、精确B7重放、跨进程writer fence。另有恢复目标占用冲突和Linux Core Python能力缺口，必须在首次真实apply前协调。Linux和stage门均保持阻塞；以下为已读源码结论，不是新测试结果。

| 范围 | 已有代码 | 环境恢复后仍缺 |
| --- | --- | --- |
| PG存储/迁移 | drill.execute校验本机Linux engine、postgres digest，schema4 dump→恢复→固定b9迁5–7、owner/部分writer权限、另库schema4回滚、mode/容量 | 未真实执行；public checkpoint/完整应用fixture没有被当前SQL fixture覆盖 |
| 固定应用runtime | image/create_container只给PG镜像与数据/工作卷；execute只调用psql/pg_dump/pg_restore/文件命令 | 没有提供或核验Linux Core3.11、锁定依赖/import路径；不能从postgres镜像身份推导Python存在 |
| primary回填 | 固定b9有backfill_v4 CLI，外部PostgresPort.backfill与backfill_owner已有dry/apply/repeat协议 | SQLdrill没有调用；现fixture的succeeded run无result.answer，无法证明旧回复补写；须primary meaningful fixture及其他owner对照 |
| B7重放 | stage-only replay CLI已存在，Windows真实PG/护栏历史25项，固定候选底层apply_withdrawals | Linux未跑；SQL fixture只有已sent/uncertain行，无“旧dump后新增撤销/收据”变化，不能证明回放语义；需精确B7两次及绑定B3 |
| 空恢复目标 | 旧SQLdrill先restore并迁7到zhiming_core_b1_restore | B3正式生成器要求这个目标为空，无法直接顺接，禁止drop/clean/覆盖补救 |
| writer栅栏 | 固定b9真实skill_writer_lock/execute_hermes_core，Native local_fence；现portable测试替身覆盖控制顺序 | drill没有跨进程/exec入口，PG镜像没有受验证的systemd/host环境；fcntl局部证明不能代替全部unit/wrapper切换 |

## 源码定位与固定候选

`b1_linux_drill.py:39/256`明确application_backfill未执行，末尾native_host_switch未验证、B7另需入口；`b1_linux_drill_sql.py:87`fixture和`:143`权限查询仅观察SQL切片。`b1_linux_drill_transport.py:95/142`核镜像并创建PG容器，没有Python或Core依赖准备。

`core_incremental.py:45`已有回填第二次三个变更计数0的门；`core_incremental_pg.py:214`通过指定release/venv/core/bin/python调用候选backfill，原文摘要排除仅允许的元数据字段并保留旧revision。该PG port固定回环5432与受审release路径，不可直接拿宿主55481/Windowsvenv或一个“apply=true”布尔值替代新Linux应用drill。

`b1_restore_replay_worker.py:20/94`要求PG15、固定恢复库/owner、schema7 checksum、完整owners、无活跃队列/租约/其他会话，并实际调用固定b9 apply_withdrawals。它不是恢复生成器，不创建库、不迁移、不替代OS writer fence。外部回执写失败可能晚于DB提交，异常后必须停审。

`core_incremental_host.py:96`是真实fcntl排他锁，`b1_publication_native.py:58`在同一lock路径包住publication；`:84/174/239`仍硬拒Native生产restore。固定b9的deploy_core.py:278/305提供共享锁、维护门二次检查、inheritable fd穿exec。`tests/test_core_release_skill_fence.py`开头明确是portable控制流测试，锁/exec被替身包裹，不是本次Linux多进程实证。

固定发布b9a89b6f84f7bebb640de080548010859aae630c，manifest应为49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c。以下从Git原始blob只读计算，不改变包：

| 固定b9成员 | SHA256 |
| --- | --- |
| tools/backfill_v4.py | a57aafe77a95649382ce17e7ef169cc84acfed5f7c1ff602cb2417258c918fe9 |
| mingjing_core/memory/backfill.py | 053840e9a17f02d062876d88ae5961db2aa72fe636e21612591b26f0c7927e56 |
| requirements-core.lock | d945dfdf75459bfff6d2903ff5b1e3fb1983619102d806f2c969eb339482e4b9 |
| tools/deploy_core.py | 71705707a7e7dae66a3702ee289557479db82b3e699f3a1ab2216f26a1e2e109 |

固定b9 CLI输入为--dsn-env/--owner/--schema/--dry-run或--apply，不自动加载.env。只有message_metadata/search_tokens/assistant_created是第二apply应0的写入计数；assistant_existing/assistant_skipped/invalid_time可非0，不能误作二次变化。

## 推荐编排

root已裁定旧SQLdrill可增storage-preparation阶段，保留原完整SQL模式的独立语义。新阶段建专属存储、schema4合成源、实际备份与完整源状态/账本摘要，并让正式zhiming_core_b1_restore保留空；两模式互斥，目标非空仍拒绝，不删除旧资源。仅有旧immutable_snapshot（entities/outbox）不能冒充B2的全Core/public-checkpoint状态摘要。

B3由其独占生成器成为唯一restore写入者，自己恢复/迁7/最新账本实际两次回放/角色核验，绑定精确B2 backup对象，不接受上层传true。当前该工具仍在开发，不能引用为已测通过。源stage应用回填在固定b9迁7后独立dry/apply/repeat留证，非primary只核计数/摘要。顺序具体实现需root进一步授tools接点，不机械执行两条已有命令。

在B3已回放且关闭所有连接的恢复状态上，现有B7 CLI再跑两次，每次独立新0600输出。首次changed可能已是false，因为B3做了真实语义变更；必须绑定B3的dump、ledger hash、目标、候选、变化证明和恢复后state hash，明确变化归属。不能为好看伪造第一次changed=true。第二次必须false且hash相同，不复活撤销原话/事实/draw，sent/uncertain经真实Outbox claim拒绝重复，整个过程无sender。

Linuxruntime门先于应用写：实际执行解释器查询证明Linux/3.11/路径/hash、核固定锁文件及包清单/关键import来源/依赖一致性，不能只hash解释器文件而声称venv已验证。当前没有进入Linux，故**不知道镜像里是否存在合格Python**，只能确认脚本没有提供或核验它。缺则独立阻塞，不自动安装/下载/扩镜像、不加依赖；Windows PG证据不替代它。

fcntl切片只用专属临时路径和惰性合成CLI，不接DB/HTTP/模型。真实writer共享锁→exec后fd仍持有→排他在deadline内阻塞/失败→writer退出后排他可用→维护门先于配置/DB拒绝。不得mock fcntl/os.exec或仅证明线程启动。现有incremental_acceptance.check_native的五个检查名可作为核对表，但新片不直接伪装成旧stage整体验收，也不做该旧schema要求的清理删除。systemd、实际三个unit、Hermes安装及Native生产restore仍分别阻塞。

## 最小拟议接口与所有权

拟议而非已实现：`tools.b1_linux_application_drill`默认只输出计划，显式apply按preflight/backfill/replay/fence分phase，新输出不可覆盖；输入只能绑定受审operation/storage回执、固定候选目录、Linux Python、B3proof/ledger/hash。每片输出独立b1-linux-application-drill-v1观察回执，publication=false、模型/发送计数0，不是B3proof或stage Go。实际Linux/PG身份不能由参数自报。

建议新增tools/b1_linux_application_drill.py、_runtime.py、_backfill.py、_fence.py及对应tests；现有b1_linux_drill.py/_sql.py的storage-preparation接点等root分配后再做，不先占transport/B3/B6。B3独占tools/b1_restore_proof*；B6归runbooks代理；既有b1_restore_replay和publication行为本片不改。

本次只拥有并冻结`docs/v4/execplans/B1_linux_application_drill_20261021.md`和本证据两份新文档。没有新测试计数、Linuxactual文件或门解除；环境尝试限额保持已用尽，B1仍No-Go。

## 08:50 storage实现首片

root后续授权了具体tools后，实现显式`b1_linux_drill --mode storage-preparation`。缺省无apply只输出计划、0transport；原full-sql默认与原完整路径保留。新模式在schema4合成备份后停止，不调用restore/migrate_restore/0008，查询实际schema4 checksum和空目标对象数，保留zhiming_core_b1_restore给B3。查询mode为0700/0600，记录全Core/public-checkpoint状态hash算法；当前纯SQL fixture没有checkpoint或实际导出账本，所以回执明确application_ready=false、admissible_restore_proof=false及缺项，不冒充正式B2/B3。

3个首片文件为`tools/b1_linux_drill.py`、`tools/b1_linux_application_drill_storage.py`和`tests/v4/release/test_b1_linux_application_storage.py`。4个新契约目标加原22传输目标**26 passed/0.27秒**，全部使用传输替身，不是Linux PG实测。非空restore拒绝且没有drop/clean，未知mode在git/Docker前拒；Ruff/格式通过。Linuxruntime/应用bootstrap/回填、精确B7接线与跨exec worker仍在下一片，环境和正式proof门未解除。
