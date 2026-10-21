# B1 增量入口离线验证回执

2026-10-18；本机Windows；源码在P3工作树，增量入口为固定b9包之外的独立操作工具。今晚没有SSH、服务器/数据库连接、模型、渠道外发、部署、提交、推送或合并。本证据只证明离线控制流和替身边界，不是PG集成、Linux验收或生产就绪结论。

## 可复现命令与结果

工作目录`C:/Users/Administrator/Documents/Codex/zhiming-v4`。使用该目录Core隔离解释器`.venv-core/Scripts/python.exe`。在本次子进程清空`KIMI_API_KEY`、`MOONSHOT_API_KEY`，设置`LANGSMITH_TRACING=false`、`LANGCHAIN_TRACING_V2=false`和`PYTHONPATH=tests`后，运行：

```powershell
& .venv-core/Scripts/python.exe -m unittest test_core_incremental_upgrade test_core_incremental_native test_core_incremental_pg_port test_core_incremental_cli -v
```

结果：`Ran 28 tests in 1.382s`，`OK`。分组为controller 10、Native替身10、PG端口替身5、CLI 3。`test_core_incremental_support.py`仅构造明确标示合成的恢复proof，没有真实演练或测试项。已有`test_core_incremental_acceptance.py`未改、未在本次新测试命令中运行。

新增Python文件通过：

```powershell
& .venv-core/Scripts/python.exe -m ruff check --select E,F,I,B,UP,SIM --line-length 120 tools/core_incremental.py tools/core_incremental_contracts.py tools/core_incremental_files.py tools/core_incremental_host.py tools/core_incremental_pg.py tests/test_core_incremental_upgrade.py tests/test_core_incremental_native.py tests/test_core_incremental_pg_port.py tests/test_core_incremental_cli.py tests/test_core_incremental_support.py
& .venv-core/Scripts/python.exe -m ruff format --check --line-length 120 tools/core_incremental.py tools/core_incremental_contracts.py tools/core_incremental_files.py tools/core_incremental_host.py tools/core_incremental_pg.py tests/test_core_incremental_upgrade.py tests/test_core_incremental_native.py tests/test_core_incremental_pg_port.py tests/test_core_incremental_cli.py tests/test_core_incremental_support.py
```

输出`All checks passed!`、`10 files already formatted`。AST核单文件24–399行，最长函数60行；10个新增Python文件全部UTF-8/LF且无CR。未跑完整Core/v4/Charts/前端/CI。

## 证明边界

| 离线已核 | 没有据此证明 |
| --- | --- |
| 固定b9/旧7dbc、manifest与1..7迁移hash；授权scope/hash/期限和明确无模型/发送/恢复业务 | 实际服务器包、依赖环境、机名、磁盘、当前配置仍相同 |
| backup→restore审批→schema4迁7→dry-run审查→apply两次→retarget状态切片有实际替身状态变化 | 真实pg_dump/pg_restore成功，SQL与实际PG15权限/角色可用 |
| 错库/host/端口/角色、runtime提权或缺CRUD、新表权限、schema漂移、非空队列/未知会话、原文hash异常均拒绝 | 有真实PG压力/全量数据性能结果；全表摘要超过5秒会失败关闭 |
| 原文不可变收据为必要条件；候选回填子进程代码完整语法编译，外层owner事务包含前后原文核验 | 真实业务数据回填、旧来源/撤销/Outbox端到端恢复已验收 |
| Native临时文件树逐文件校验，旧wrapper与既有生成器逐字相同；旧fence代码AST漂移即使重哈希也拒绝 | 实际7dbc包和原始退役备份与A一致，或跨进程锁能覆盖实际exec |
| 临时unit/技能文件发生固定路径替换，manifest最后写；退役stub/原始备份保留；不整体restart Hermes | 运行中Hermes缓存刷新、真实systemd drop-in/进程终止/开机触发完全验收 |
| 默认CLI仅校验；apply无native/审批拒绝；原始错误/输入不回显；异常、迁移后中断仍关闭 | 断电/磁盘满/部分retarget的真实Linux故障恢复已经完成 |

Windows Native测试显式注入可信POSIX权限模型、Linux/root/机名、12GiB容量、锁、PG与命令端口，替身不是实际主机证明。测试同时阻止subprocess、网络、系统exec逃逸；PG连接函数也被阻止，绝无偷偷使用真实服务器的回退路径。CLI测试禁止创建Native适配器或进入execute。

## 固定输入与源码hash

固定发布候选：`b9a89b6f84f7bebb640de080548010859aae630c`；旧包：`7dbc951eaffebd3d812169865eaefcde16a00ed9`。按本机Git b9的636个原始blob重算release manifest SHA256：`49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。旧manifest仅固定A安全元数据`22edb794d44ab45e2b234edd3f5ed886879fe88d23392977fee63e1085a3859c`，没有访问服务器补证。

控制器hash：`81216d0d9e6ba2dad1df73518278190414a4141ec794e9004b853b4b7bc01920`。以下为原始字节SHA256；root若修订任意`core_incremental*.py`，必须重核控制器hash与审批。

| 文件 | SHA256 |
| --- | --- |
| `tools/core_incremental.py` | `7f5bb4966c04c6cabb4e56ab367b09dd419a6b5d5663e403f122d70ef6c67cc7` |
| `tools/core_incremental_contracts.py` | `19341450536a0e4e58957055e3633e906bd768b3e377f821165493c2bcd4479b` |
| `tools/core_incremental_files.py` | `b2d651d503496e1c332e8e1358eb8efc05851e98ca4e07a944527e756ca1569a` |
| `tools/core_incremental_host.py` | `960a766e1ee3d4fb6bb9c6a8d44d341dbe494487ef142e24ede2ab575c4d1aeb` |
| `tools/core_incremental_pg.py` | `69c8334976d1bb11f8988cddd64f2d5a12921060d4862c583095c4fe1144d80a` |
| `tests/test_core_incremental_upgrade.py` | `8e7144b715829914b2fd7723905668821caeb68bc50754135a8960e9ac6ec3af` |
| `tests/test_core_incremental_native.py` | `ee22683443c416903fee1990ec8a8471f81061badae36bd29b4d97dfc43e59e8` |
| `tests/test_core_incremental_pg_port.py` | `5e1764ccd23e4f2b1c6f6219e907d25d3c34089cd9f4cd12cb1111590c6d1a54` |
| `tests/test_core_incremental_cli.py` | `5bb22af3048f7637a67ec1827daeb0d9a5aa2d10a3a7224fad3e819d9b395edd` |
| `tests/test_core_incremental_support.py` | `65c00cba4be7fdcface7c60ae524870059a8d02ee0e6a639150619cbc6798400` |

## 后续门

根代理/同伴复核补充的实际执行阻断：LocalCommands当前使用白名单命令名并继承PATH，真实Linux适配前须固定/核验systemctl、pg_dump等实际二进制；release校验刻意排除venv，候选解释器与依赖完整性尚未形成机器可核证明；显式owners审批列表还需与A的stage17/live2及最新全库身份核对，不得漏回填后宣布完成。这三项不由替身全绿消除，实际B执行仍No-Go。

容量选择明天由用户决定；扩容/整理对照见`B1_disk_options.md`。B1保持b9、tzdata随B2。Linux隔离替身的SQL/权限、真实精确备份恢复proof生成、跨进程fence及retarget中断演练均未完成，需另审本地/合成环境范围。任何stage/live部署、重启、模型或外发都仍需用户针对那一次操作的授权，不能凭本工具存在而越过B/D/E门。
