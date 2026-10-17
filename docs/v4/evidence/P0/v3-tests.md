# P0：旧 Core v3 与前端基线

验证日期：2026-10-17（UTC+08:00）。分片开始于 12:55:12，对应源提交 `cf2c572c2563ef57fe962f3ac7e2f1c94b689066`。旧 `tests/test_core*.py` 相对 `b996f42` 没有修改。

结果：旧 Core 去重后 **553/553 项有通过证据，0 跳过、0 遗留失败**；前端六项检查全部退出 0。首次恢复验收有 1 项环境失败，补齐 PG 工具 PATH 后，其所在模块 3/3 通过。没有为通过测试修改旧业务代码或旧断言。

## 环境与边界

- Core / Charts：两个独立 CPython 3.11.16 环境，分别原样安装 Core+Test、Charts 锁文件；两者依赖一致性检查均通过。
- Node 22.23.3；`npm ci` 成功，官方 ZIP 的 SHA256 已核对。
- PostgreSQL 15.19：本项目新建 cluster，只监听 `127.0.0.1:55480`。
- 三个分片分别使用 `p0_legacy_0`、`p0_legacy_1`、`p0_legacy_2`，不共用业务 schema 或 public checkpoints。
- 测试进程显式清空 Kimi、Moonshot、飞书凭据；使用合成资料与已有模型/传输替身，真实 PG 与真实排盘未替换。
- 没有连接 stage / live、操作生产服务或发送真实飞书消息。

可复用的安全环境设置、PG 启停方式见 [local-environment.md](local-environment.md)。原始安装和运行日志保留在本机忽略的 `private/p0-logs/`，不进入仓库。

## 旧 Core 覆盖

原始命令为：

```powershell
.venv-core\Scripts\python.exe -m unittest discover -s tests -p 'test_core*.py' -v
```

串行试跑初段通过，但考虑大量真实排盘子进程的耗时而主动中止；该试跑不计作完整套件通过。正式运行使用同一 `unittest` discovery 结果，按模块分配到三个进程：模块先按测试数降序、模块名升序排列，依次放入当前测试数最少的分片，分片内按测试 ID 排序执行。工作站辅助脚本位于忽略的 `private/run_legacy_shard.py`：

```powershell
.venv-core\Scripts\python.exe private\run_legacy_shard.py --shard 0 --shards 3
.venv-core\Scripts\python.exe private\run_legacy_shard.py --shard 1 --shards 3
.venv-core\Scripts\python.exe private\run_legacy_shard.py --shard 2 --shards 3
```

每个进程各自收集 553 项，只执行所属模块。完整测试 ID 及原始分片结果见 [v3-test-manifest.json](v3-test-manifest.json)：分配总数 185 + 184 + 184 = 553，集合去重仍为 553，无重复或遗漏。

| 运行 | 执行数 | 首次通过 | 环境失败 | 跳过 | unittest 耗时 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 分片 0 | 185 | 184 | 1 | 0 | 150.388 秒 |
| 分片 1 | 184 | 184 | 0 | 0 | 468.830 秒 |
| 分片 2 | 184 | 184 | 0 | 0 | 299.755 秒 |
| 恢复验收重跑 | 3 | 3 | 0 | 0 | 1.128 秒 |

分片 0 的唯一首次失败为 `test_core_release_restore.CoreReleaseRestore.test_older_backup_replay_erases_direct_draw_ids_context_checkpoints_and_protects_receipts`。测试通过 `shutil.which` 查找真实 `pg_dump` / `pg_restore`，新工作区尚未把旧工作区的 PG 二进制目录加入 PATH，因而在执行备份前失败。修复仅调整当前进程 PATH，未修改代码、数据或断言。

修复后执行：

```powershell
.venv-core\Scripts\python.exe -m unittest discover -s tests -p 'test_core_release_restore.py' -v
```

结果为 `Ran 3 tests in 1.128s`、`OK`，覆盖真实合成备份/恢复与撤销重放。重跑的 3 项已经在 553 项内，不能重复累加。最终去重通过数为 553，遗留失败为 0。

## 前端检查

以下均在独立 Node 22.23.3 PATH 下执行：

| 命令 | 结果 | 过程耗时 |
| --- | --- | ---: |
| `npm test` | PASS，退出 0 | 0.382 秒 |
| `node tests/dom.test.cjs` | PASS，退出 0 | 2.332 秒 |
| `node tests/report-settings.dom.test.cjs` | PASS，退出 0 | 1.026 秒 |
| `node tests/method-limits.dom.test.cjs` | PASS，退出 0 | 0.477 秒 |
| `node --check static/app.js` | 退出 0 | 0.036 秒 |
| `npm run build` | 构建成功，退出 0 | 0.857 秒 |

构建后 `static/vendor/utilities.css` 与 `package-lock.json` 均无变化。DOM 检查使用 JSDOM，没有真实浏览器布局引擎；以上结果不能充当响应式截图或视觉验收。

## 已知风险与未验证

- `npm ci` 审计摘要为既有依赖 8 项漏洞（2 moderate、6 high）；没有自动升级依赖或修改锁文件。
- 构建提示 `caniuse-lite` 数据过期；构建仍成功，没有修改其依赖数据。
- 本文件仅记录旧 Core / 旧前端的本机基线，不代表真实模型、stage、生产发布或 v4 产品能力通过。真实模型基线由 P0 独立评测报告记录。
