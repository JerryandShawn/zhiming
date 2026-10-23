# B1 B3 恢复证明生成器：本机证据与放行边界

本轮只在 Windows 本机隔离 PostgreSQL 15 上运行合成测试。没有 Linux 演练、stage/生产访问、SSH、模型请求或飞书发送。指令板 v2 与 30 号 **No-Go** 保持有效；本文件不能解除 B1 本机 Linux 门。

## 实现的实际流程

`tools.b1_restore_proof` 缺省验证 request/backup/dump/两份 raw ledger hash、固定 b9 636 个 blob 与七条迁移，不创建连接或子进程。只有 `--apply --quiesced --output <新绝对路径>` 才执行；输出存在、symlink、正式父目录非 0700 时在数据库操作前拒绝。B2 backup 对象和源状态 hash 都被绑定，不接受调用者填写阶段 success 布尔值。

apply 自己观察独立 owner/writer 的 PG15 回环身份、空目标和零其它会话，运行受审绝对 pg_restore（二进制原始 hash/版本核验、单事务、no-owner/no-acl、无 clean/drop），比对恢复后的 schema4 七迁移前缀 1–4 与 B2 全表状态 hash。接着在全新进程只导入固定 b9：原生迁 0005–0007、重授运行权限、最新撤销/收据 apply 两次并核第二次 changed=false、前后状态 hash 连续，查询撤销实体/固定牌/已撤销 run checkpoint 与 sent/uncertain 账本。最终 writer 必须无成员关系/ownership/系统权限/持久或临时 DDL，两张迁移账本只读、业务/checkpoint CRUD 实际有效。

正式模式只允许 stage 的 `zhiming_core_b1_restore`、固定 `/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c` 和其 `venv/core/bin/python` 词法路径，保留 venv 发现语义；manifest 成员/祖先和解释器须 root 所有且不可组他写。任何连接前都交叉核 owner/writer 规范化 hostaddr/port/database 一致，拒绝两本机实例混用。平台来自实际 Python/PG 查询，不能通过 CLI 的 platform 参数或输入 JSON 升级。source/candidate/输入再次核验后才构造 `b1-isolated-restore-proof-v1`，并调用增强后的正式 `validate_restore` 自检 ABI；失败不返回或写入 admissible=true。

Windows `--local-drill` 只允许随机 `b1_restore_proof_<32hex>` 数据库、同名独立 owner/writer、55480/55481，输出 **`b1-local-restore-drill-v1` / `admissible=false`**。实际本地回执已被旧 `validate_restore` 拒绝。即使在 Linux 显式选择 local-drill，也不能输出正式 schema。生成器只证明观察时目标为空，字段 `database_creation_observed=false`；创建证据由获准 B0/B7/编排步骤另交，不能把 empty 写成新建实证。

## 可核的 CLI

空目标门现同时拒绝 relations/functions、非默认 namespace、public 用户类型/域和非默认扩展。两个真实 PG 反例证明：预置 enum 或没有表的自定义 schema 都在 pg_restore 前拒绝，原对象保持存在，不清空或覆盖来伪装空库。

以下接口已通过 `--help`，其中路径/hash 必须由 B2 及获审包实际填写；DSN 不进入 argv：

    python -m tools.b1_restore_proof --request "$REQUEST" --backup "$BACKUP_OBJECT" --dump "$DUMP" --backup-ledger "$BACKUP_LEDGER" --ledger "$LATEST_LEDGER" --ledger-sha256 "$LATEST_LEDGER_RAW_SHA" --database zhiming_core_b1_restore --candidate-source "$RELEASE_DIR" --candidate-python "$RELEASE_DIR/venv/core/bin/python" --pg-restore "$REVIEWED_PG_RESTORE" --pg-restore-sha256 "$PG_RESTORE_RAW_SHA"

缺省命令的结果是 valid=true/apply=false/database_connections=0。正式 apply 再追加 `--apply --quiesced --output "$NEW_PRIVATE_PROOF"`；今晚/本轮没有执行正式模式。`B1_PROOF_OWNER_DSN` 与 `B1_PROOF_WRITER_DSN` 仅由受保护 loader 注入，拒绝隐式 libpq PGHOST/PGHOSTADDR/PGPORT/PGDATABASE/PGUSER/PGSERVICE/PGSERVICEFILE/PGSYSCONFDIR/PGOPTIONS/PGPASSFILE/PGPASSWORD，并显式固定 hostaddr/port。可用 `B1_PROOF_PGPASSFILE` 指定受保护绝对文件；缺省显式指向规范化系统 null 设备，禁用 `~/.pgpass` 回落，不回显文件内容。

子进程只传所需本机 DSN 与固定安全系统变量，清模型/飞书/追踪凭据、关闭追踪。Python 子进程固定 `-I -B -X pycache_prefix=<绝对系统null>`：`-B` 仅禁止写 pyc，仍可能读缓存；实际合成等 mtime/size 污染 pyc 对照证明普通 `-I -B` 得到 poison，新前缀得到 source 且不改旧缓存。不创建/删除候选缓存，不修改固定包。该实际实验在 Windows/锁定 CPython 3.11 上运行，不宣称 Linux 通过。pg_restore/SQL/候选异常只返回固定安全码；不会把 INSERT 行、原话、DSN 或 stderr 放进 CLI 回执。最终输出独占 0600 创建并 fsync，不覆盖；写盘失败可能发生在 PG 提交后，须保持现状停审，不能自动重试。

## 验证记录

使用已锁定 Core Python，清模型/渠道 key 并关闭追踪，显式指定本机可丢弃 PG15 管理连接。只有一个窄测试进程；夹具新建两个随机专用 source/restore 数据库和两角色，结束仅清理自己本次创建的精确资源，不碰既有业务库/共享 PG 服务。所有 dump/旁账只含合成测试数据，留在 private/临时目录，不入 Git。

    python -m pytest tests/v4/release/test_b1_restore_proof_contracts.py tests/v4/release/test_b1_restore_proof_pg.py -q --tb=short --junitxml=private/b1-restore-proof-20261021/target-<轮次>.xml

首轮 30 passed / 32.86 秒；第二轮补 CLI 新输出、账本授权、其它会话和活跃 run 反例后 33 passed / 43.37 秒（25 纯契约、8 真实 PG）。只读审计随后发现隐式 libpq 路由、正式源码/解释器路径信任两项缺口，修复后 46 passed / 45.31 秒。以上是历史候选，不当作最终文件的成绩。

第三轮 TEMP 有效权/真实临时表 DDL 探针修复后 47 passed / 46.86 秒；再禁用 libpq 默认 `~/.pgpass` 回落后 48 passed /45.58 秒。补 owner/writer 同实例前置门与正式消费者 ABI 自校验后 51 passed /77.38 秒；强化空目标目录并补 enum/空 namespace 反例后 53 passed /106.43 秒。最后隔离旧编译缓存并加实际污染 pyc/argv 两个反例。**最终候选 55 passed / 109.72 秒（44 纯/实际本机 Python 契约、11 真实 Windows PG15），0 failed / error / skipped / warning**，源码指纹如下。没有把失败改成 xfail 或删除断言；上述审计发现均保留新增反例。最终原命令使用 `target-7.xml`；仅测试文件最终 Ruff 格式调整后两个 cache node 再验 2 passed /0.21秒，属于55的子集，不相加成57。

真实合成流程观察到：PG server_version_num=150019；迁移完整 1–7；第一遍 changed=true、第二遍 false 且状态连续；2 owners、1 deleted draw、1 tarot tombstone、2 protected receipts；24 张表权限核验，5 个真实拒绝探针（Core/public CREATE、TEMP CREATE、两个迁移账本 INSERT）。独立 raw 本地回执 created_at=`2026-10-21T09:09:59.147737+08:00`，schema 为 local/admissible=false，没有正式签发。

| 原始证据（不入 Git） | bytes | SHA256 |
| --- | ---: | --- |
| `private/b1-restore-proof-20261021/target-7.xml` | 9284 | `940edfa20df841c204175cdab7aeb67dda8fa33c5b805bdf70f98f7a7c5cc1a0` |
| `private/b1-restore-proof-20261021/observed-local-receipt-55.json` | 4085 | `3689fcfdd96a941191b90ebcc741eb74788e5c473af4f873bedd6cfa597fe547` |
| `private/b1-restore-proof-20261021/cache-confirm.xml` | 585 | `69fbb7de2cda2e8f48a3ff6595b90df565b70a5f84805a375da391494f3c616a` |

JUnit 原始 suite 时间 `109.702` 秒，控制台 `109.72` 秒，保留各自口径。JUnit 时区原值 `2026-10-21T10:09:47.629944+09:00` 明确换算为北京时间 `09:09:47.629944+08:00`，没有把本机东京时间当北京时间写入。旧 target-1/2/3/4/5/6 及 observed-local-receipt-46/48/51/53 保留历史，不覆盖冒充最终。

最终生成器五模块对象 hash：`a6477f2fbd4a1f3a9ee49f5a2c2e205024b7380ea595cf2103bea5195dd231bb`。严格 Ruff E,F,I,B,UP,SIM/120 与 format check 全过；8 个 Python 文件均 ≤314 行，最长函数 53 行。没有新增依赖或迁移。

| 源文件 | bytes | SHA256 |
| --- | ---: | --- |
| `tools/b1_restore_proof.py` | 6177 | `077a9d69d3304d848d6e6bec289c6d41be1719324b382664c8c87684eb5ab4cc` |
| `tools/b1_restore_proof_contracts.py` | 8160 | `6f4c1edebea7d4d90f9050f726ebb39539487678315cddafb3f6ec33c18c1751` |
| `tools/b1_restore_proof_pg.py` | 8722 | `5adc5309d10de7b24d6f50af47f80ee4785b4061c5cb7cd9e0dada9bb00c80a0` |
| `tools/b1_restore_proof_process.py` | 5410 | `18262ffb2d20388fea5c164dcc3f8e9359206311d6601620ab8c7158c7a006a9` |
| `tools/b1_restore_proof_worker.py` | 6992 | `a543353912ee3903fcd85ddf2cf10a1342316b45b2342e7e05097a94bf323a75` |
| `tests/v4/release/b1_restore_proof_support.py` | 8327 | `6fe12dbddd42b78ba14f881a3e382ef3930a7b2e25b70bd512ffd6ed1ecad95c` |
| `tests/v4/release/test_b1_restore_proof_contracts.py` | 13420 | `b70611b3d7f7eb04b1f9f689360407a236eb542fe456ae7a188c29a46abf2c4c` |
| `tests/v4/release/test_b1_restore_proof_pg.py` | 9785 | `9fe7a3444dc9eb7a162dbd371f6ff844a069c6608cb2b70396b1744da8ce46eb` |

## 未验证与阻塞

当前测试支撑仍有可移植性缺口：PG_BIN 固定 Windows 目录，真实 PG 组必须显式 B1_PROOF_TEST_ADMIN_DSN 且只接受本机 55480/55481；CI 默认没有该变量会跳过 11 项。纯契约 inputs 也复用该工具路径及 legacy materialize，依赖本地完整 b9 Git 对象，因此 Linux/浅克隆 CI 还可能直接失败，不能仅描述为全部 skip。此次 53 是明确 Windows 本机目标证据；尚无这些新工具的 CI/全库自动执行保证，不继承 09:00 固定 wire 全量结果。下一独立窄片再处理显式 PG15 工具路径/可移植纯夹具/已核候选来源，不装新依赖、不放宽正式 PG15/新库边界，本片未改 CI。

没有真实 Linux/POSIX、容器镜像 digest、正式目录/venv 信任链、跨进程 fcntl、systemd 或服务器操作。正式 proof 尚未生成，不能把 Windows 回执改 schema/数据库名或手填 true 供放行。现旧 SQL drill full 路径预消耗正式恢复库的问题由另一独立 storage-preparation 轨处理；B3 保持空目标强门，不为接线放宽、不删库重建。

完整 B1 仍须补 Linux runtime 能力、primary 回填 dry-run→apply→二次零变化及 writer fence 等证据。源 dump 必须已含四张 public checkpoint 表，纯 psql schema4 dump 不具备这项应用能力。任何异常保留恢复现场；本工具不声明创建数据库、生产回滚或恢复服务的权限。

## 文件范围

独占五个 `tools/b1_restore_proof*.py`、`tests/v4/release/b1_restore_proof_support.py` 与两份 `test_b1_restore_proof_*.py`、对应 ExecPlan 和本文。不改 b9、迁移、旧 replay、runbook 或其它代理的生产文件；consumer 的放行契约加固由另一代理单独交付。
