# B1 增量运行角色：TEMP 权限实证与最小修复

2026-10-21 09:37 +08:00，北京时间。固定 b9 包、迁移和正式身份/路由门不变；30 No-Go。仅 `core_incremental_pg.py::_runtime_safe` 的只读聚合 SQL 增加 TEMP 判定，没有自动 REVOKE 或正式库连接。

## 先红后绿

旧检查已拒 schema/database CREATE、owner/继承与账本写入，但遗漏允许创建临时表的 TEMP。新增两个真实 PG15 反例，分别将 TEMP 授给专属随机 writer 或 PUBLIC，其余授权维持安全；直接执行该方法的真实权限 SQL。旧实现均错误返回 true，**2 failed /24.23秒**。新增一项 `has_database_privilege(current_user,current_database(),'TEMP')` 后，同一反例均返回 false；撤回测试新增授权后均恢复 true。

修复后组合为新实际 PG 2项、路由62项、旧 PG port5项、实际合成 pyc4项，**73 passed、4 subtests passed /21.22秒**，exit0，0失败/错误/跳过。开始09:34:52、结束09:35:14（+08），原日志和原失败均独立保留。Ruff E/F/I/B/UP/SIM、120格式和diff检查通过；新生产只加一行，未修改任何旧断言。

    python -m pytest tests/v4/release/test_b1_incremental_runtime_temp_pg.py tests/v4/release/test_b1_incremental_pg_routing.py tests/test_core_incremental_pg_port.py tests/v4/release/test_b1_existing_candidate_bytecode.py --assert=plain -q --tb=short

## 实际边界

显式使用既有本机 PG15、127.0.0.1:55480 与固定 b9 源；B3 夹具各自创建随机 source/restore 库及独立角色，真实 dump/restore/迁7/撤销重放后验证 writer 安全，再只对本测试随机库授/撤 TEMP。两项均保留 PUBLIC 与 writer 独立反例，finally 撤回新增授权，既有夹具只清理自身精确随机资源。生产工具没有新增权限写逻辑。

这两项测试只直接调用 `_runtime_safe` 的权限 SQL，使用已知随机库的真实 psycopg 连接。测试对象没有配置或调用控制器 connector/snapshot/NativePort，未构造 stage 连接；不会把本机55480放宽为控制器允许端口。后者的严格5432/固定库路由由独立62项契约保护。本结果不能证明 Linux、正式 stage、跨进程 fence、systemd 或整个 B1通过。

所有测试清供应商凭据/隐式 PG 环境，关闭追踪与飞书，传 TZ=Asia/Tokyo；证据时刻以显式+08记录。原 JUnit 自报时区为+01：02:34:15与02:34:53分别等于北京时间09:34:15与09:34:53；原件不改为假定的主机+09。测试未依赖当前系统时区计算验收结论。

## 精确原件

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| tools/core_incremental_pg.py | 14336 | c90a83aa164deadfecd17bf0c6cba3b84f373379b9ec6728210a2b8c3d38f33f |
| tests/v4/release/test_b1_incremental_runtime_temp_pg.py | 1780 | 6a2f1f4600cbe5d1c4c50e03f5c020829f6cc6ecf1b0ed9089f8da1c20e199f4 |
| private/b1-restore-proof-20261021/runtime-temp-before.xml | 2296 | 0b1d60488cf4772ee812690a349af7ff0888343b834631b610a3841c33f4f294 |
| private/b1-restore-proof-20261021/runtime-temp-after.xml | 12627 | aaa1299d81f060ec0b55b33858a8484e037d9b83be2b6309686c62d6b9e89727 |

JUnit修复后tests=77包含4个子测试，不能写成77主用例；73也不与之前71或B3/App数字累计。旧失败原始日志只留私有目录，公开报告仅固定错误与计数，不复制 DSN/口令/正文。

真实模型、服务器、飞书0；不合并 v4/main/main。正式 writer 若有 TEMP，控制器将停止，必须交审而不是自行撤权限重试。
