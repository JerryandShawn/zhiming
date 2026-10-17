# P2 stage 上线准备（仅计划，未执行）

本文件基于 `docs/CORE_V3_RELEASE.md` 与 `tools/deploy_core.py` 的固定 Git 对象、隔离迁移角色、备份和维护恢复约束。夜间没有连接 stage/生产，没有部署、服务重启、真实模型或飞书发送；执行本计划须另得用户针对 stage 的明确授权，生产切换仍须大脑验收后另行授权。

## 固定输入与前置核对

使用经过最终 CI 的 40 位 P2 提交，以及同一提交的构建清单和测试证据。P1 若先验收合并，先 rebase 并重跑；其中 coverage 7.11.0 必须保留，重新生成 Core/Test 全哈希锁，不得漂移既有依赖版本。

操作者在 stage 机器上以受保护 0600 环境文件提供迁移 DSN、DML 运行 DSN、owner 及独立 Charts Python；不把连接串放入命令参数或输出。确认数据库严格为专用 `zhiming_core_stage`、PG15、回环连接；迁移角色与运行角色不同，后者非 superuser、无 CREATEDB/CREATEROLE/CREATE。确认维护门只针对 stage；保持真实 Feishu 与定时投递禁用。主仓的 `deploy_core.py install` 针对 live，不能把它误作 stage 增量迁移命令。

`tools/deploy_core.py bundle/prepare` 可用于固定源码打包及双环境准备，遵循现有 release 文档的参数和清单校验；本计划不修改其部署目标或绕过发布门。此刻块的 timezone 缺省 Asia/Shanghai；不在上线时替用户决定其他时区。

## 备份与只读盘点

先停止 stage 的写入与投递，等待运行结束，保存最新无正文撤销账本及投递 sent/uncertain 状态。使用 stage 迁移角色将完整 PG 做 custom 格式备份到受保护目录，记录 SHA256、PG 版本、固定提交及原 schema_migrations 版本/校验和；同时备份渠道绑定和运行配置，正文和密钥不进入 Git/PR/公开日志。

通过受保护 PGPASSFILE 提供认证时，备份形态如下；路径和端口由操作者确认后代入，不在夜间执行：

    pg_dump --host=127.0.0.1 --port=<stage端口> --username=zhiming_core_migrate_stage --dbname=zhiming_core_stage --format=custom --file=<受保护目录>/before-p2.dump

记录 active 消息数、user/assistant 分布、成功 run 数、已撤销/已删除 run 数、事实和来源 revision 摘要、原 sent/uncertain 数。不得为了达到预期数量导入已撤销来源或助手输出事实。

## 迁移与重新授权

仅以迁移角色运行 P2 的 `PostgresRepository(..., initialize=True)`，目标 schema 为既有 mingjing_core；初始化接受连续已知校验和前缀并执行 0005–0007，未知未来版本、缺口和漂移拒绝。先核对实际 `core_runs` 调用约束名；保留 v3 应用预算，仅数据库取消 calls<=call_limit。三个迁移与账本在一个事务内完成，错误即回滚，不能手工删迁移记录重试。

显式进程环境 CORE_MIGRATION_DSN 配置完成后的命令形态：

    python -c 'import os; from mingjing_core.repositories.postgres import PostgresRepository; r=PostgresRepository(os.environ["CORE_MIGRATION_DSN"],schema="mingjing_core"); print(r.verify_schema()["version"]); r.close()'

随后用同一迁移连接调用 `repositories.permissions.grant_runtime_tables(connection, runtime_role)`，重新授所有业务表及序列权限，并确认新 core_run_steps/core_run_events/core_embeddings 具备 CRUD。迁移账本只读；运行角色无 schema CREATE。原 LangGraph public checkpoint 及其权限仍保留，不执行 0010 或删除旧运行记录。`deploy_core.py` 的既有最终授权步骤已复用此函数，不能只在迁移前授权一次。

## 回填 dry-run 与 apply

先运行只读 dry-run：

    python tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner <已核验owner> --dry-run

核对 message_metadata、search_tokens、assistant_created/existing/skipped、invalid_time 与少量样例 ID。只打印计数/ID，不打印聊天正文。助手数与成功运行数存在差异时，应逐项解释撤销、删除、已有助手或缺失来源；若无法解释，保持维护状态，列为待用户/大脑处理，不能盲目继续。

数量合理且授权仍有效时执行 apply，再重复 apply：

    python tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner <已核验owner> --apply

第二次必须新增 0 条助手消息，元数据与 tokens 修改为 0；保留原用户正文、来源时刻与 revision、原 conversation_id，并增加 origin_conversation_id/thread_id/UTC at_ms。回填在 owner 事务锁中，意外中断整次回滚，可用同样命令复跑，不得换稳定 ID 绕过去重或墓碑。

## 冒烟检查与放行

以 DML 运行角色启动固定 P2 版本，只读 verify_schema 通过且不会做 DDL。使用 stage 合成 owner 检查日期、星期、农历、节气/交节、2027 未公布标记和 owner 时区；检查双向跨渠道/跨话题历史、/api/history 原有 cursor/meta 结构与助手去重。验证助手输出不能保存成用户事实；撤销源原话后助手被脱敏、向量和检索不再返回撤销内容，备份重放撤销仍成立。

报告 dry-run 检查实际 selection.date、period.start/end、原准备/投递时间及不重发账本；不发送真实飞书。真实 T/R/M/S 评测必须等 WS1 v2 同口径基线及大脑决定，并单独获准后再跑，不能把 scripted 或替身结果作为实测成绩。检查通过后才按 stage 授权范围解除 stage 维护门，生产仍保持原状。

## 失败与恢复

事务内迁移/回填失败先保持 stage 写入和投递关闭，修复后重新执行；不修改 0001–0004，不删除账本记录，不执行向下 SQL。迁移成功后旧版本会拒绝新 schema，因此不能直接切旧代码“回滚”。优先采用已核验的新版本向前修复。

必须恢复备份时，仅对专用 stage 目标执行经过批准的 custom dump 恢复，保持所有写入和投递关闭，先恢复最新撤销账本和 sent/uncertain 收据，再核对其他有效变更；确认备份 schema 与配套代码一致。绝不重启旧 Hermes 解释循环，不恢复 SQLite/JSON 权威，不把 sending/uncertain 变成自动重试。公开回执只给计数、哈希和状态，不附受保护备份、正文或凭据。

## 尚需决定或提供

用户：stage 的具体访问授权、受保护配置与维护时间；本夜未请求或获取。大脑：WS1 v2 基线是否有效及 P2 真实比较的执行时机；P1 验收后 rebase 顺序。任何异常盘点在实际 dry-run 后另列，当前本机合成验证不能代表 stage 盘点或部署完成。
