# Core v3 固定版本发布与维护回退

网站、塔罗、飞书与报告一次切到独立 Core v3。生产 PostgreSQL 15 是唯一权威，LangGraph 执行统一 ConsultationService。脚本 `tools/deploy_core.py` 只在本地生成包或在已授权的服务器本机执行，不连接 SSH，不发送验收消息。发布前完成审计、隔离迁移、真实计算、模型和前端验收；维护窗口只做最终一致性迁移与切换。

## 固定输入

发布使用已审阅的 40 位 commit，路径必须为 `/root/zhiming-core-releases/<commit>`。`bundle` 要求 HEAD 完全相符且工作区干净，通过 ls-tree + cat-file 原始 Git blob 打包普通文件，并记录逐文件 SHA256 与 Git blob SHA1。Windows working tree 或 archive 的换行转换不进入发布包。`prepare` 同时核对整个包 SHA256、成员清单、逐文件哈希和 commit；拒绝路径穿越、软链接和重复成员。运行后产生的 venv、缓存、计算验收文件不改变源码清单。

专用数据库为 `zhiming_core_stage` 和 `zhiming_core_live`，运行角色同名；分别使用独立迁移 owner，例如 `zhiming_core_migrate_stage` / `zhiming_core_migrate_live`。由现有 PostgreSQL 管理员**新建**这些数据库和角色，使用 SCRAM 口令与本机连接，保留其他数据库。迁移角色拥有专用数据库及 `mingjing_core` schema；运行角色不是 superuser，没有 CREATEDB / CREATEROLE / schema CREATE。最终迁移还通过 PostgresSaver.setup 创建 `public.checkpoints/checkpoint_blobs/checkpoint_writes/checkpoint_migrations`，授运行角色两个 schema USAGE、业务表及三个 checkpoint 数据表 CRUD；`mingjing_core.schema_migrations` 与 `public.checkpoint_migrations` 仅 SELECT。运行入口只读核对版本和 Core 迁移哈希；有待执行迁移时拒绝启动。

密钥留在服务器已有受保护环境文件，不放入 Git、打包产物或命令参数。`--env-file` 可重复，按顺序覆盖；保留 `/etc/systemd/system/mingjingtai.env` 的网站 token 和模型配置、`/root/.hermes/.env` 的渠道凭据，最后加专用 Core 环境文件。文件须为普通文件、权限 0600，内容是 `NAME=value` 或带引号的单行 literal，不使用 export、变量展开或命令替换。最终 Core 文件应明确给出：

```text
ZHIMING_DATABASE_URL=<专用 live 数据库运行角色连接串>
MINGJING_OWNER_ID=primary
CORE_DB_POOL_SIZE=4
CHART_PYTHON=/root/zhiming-core-releases/<commit>/venv/charts/bin/python
ZHIMING_MEDIA_PATH=/root/zhiming-core-media
CORE_FEISHU_ENABLED=true
LANGSMITH_TRACING=false
```

`--migration-env-file` 另指向只含迁移 owner 连接配置的 0600 文件，只在迁移进程最后覆盖运行 DSN，不写入 systemd unit。脚本核对其数据库、host、port 与运行配置相同且用户不同。生效连接串、token、API key 不输出到终端。旧 env 若存在旧计算路径，用最后的 Core 文件明确覆盖。

受保护 `bindings.json` 使用迁移 CLI 的显式绑定列表：`channel/external_id/owner/subject/binding_kind`；飞书作者用 user 绑定，目标为群聊时用 chat 绑定，报告任务用 report/task 绑定。不能根据消息正文或手机号猜 owner。`legacy-job-ids.json` 是已核对的 **4 个**既有晨报、周报、月报、季报 cron ID 字符串列表。脚本同时校验对应任务包含 `zhiming` / `report_pipeline` / `知命` 标记，绝不禁用其他 Hermes cron。

## 验收与构建

在同 commit 的隔离 stage DB 重复迁移同一份受保护快照，检查 ID、撤销账本、旧报告送达账本与绑定一致。旧未确认档案不得自动变成出生事实；旧 waiting 正文不得进入发送队列。旧已送达报告以原 business ID、receipt 留档阻断重复发送；曾尝试而送达不明的记录保留 uncertain。旧未尝试记录仅保留原 due，新 Core 生成并校验后才可替换。

完成真实 PostgreSQL 集成测试、真实三盘无 skip 计算、受控真实模型验收，以及 npm/DOM/构建检查。计算环境独立安装 `requirements-charts.lock`，业务环境安装 `requirements-core.lock`，两边运行 pip check。真实模型验收只在 stage；飞书 transport 验收使用替身，不向生产飞书发额外测试消息。

验收文件至少包含如下字段；任一 false、非零 skip、错误 commit 或错误数据库均阻断 freeze/install/publish。验收证据中另记录测试统计、迁移摘要和对应报告文件哈希，不能仅凭这个布尔清单宣称功能已验收。

```json
{
  "commit": "<40位已审阅SHA>",
  "database": "zhiming_core_stage",
  "calculator_skips": 0,
  "stage_accepted": true,
  "frontend_passed": true,
  "migration_replay_passed": true,
  "live_provider_smoke_passed": true
}
```

本地生成包后，经授权渠道传到服务器，记录输出的包 SHA256。以下是服务器 Bash 的参数模板，替换已审阅 SHA 和包哈希；路径变量不含任何密钥。

```bash
REVIEWED_SHA=<40位已审阅SHA>
RELEASE_DIR=/root/zhiming-core-releases/$REVIEWED_SHA
python tools/deploy_core.py bundle --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --source . --artifact /protected/core-release.tar.gz
python tools/deploy_core.py plan --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR"
python tools/deploy_core.py prepare --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --artifact /protected/core-release.tar.gz --artifact-sha256 <已核对包哈希>
CORE_PY=$RELEASE_DIR/venv/core/bin/python
```

`prepare` 创建两套 venv 并运行合成计算验收，不改旧网站、消息入口、数据库或报告任务。外部依赖缺失、pip check 失败或真实计算 skip 会阻断后续流程。

## 维护窗口与切换

`freeze` 先安装 nginx 维护门，再停旧报告 service/timer，备份 Hermes config/cron 并仅设置 `platforms.feishu.enabled=false` 与 4 个已核对任务的 enabled=false，重启 Hermes 保留其他渠道，然后停旧网站。此显式 false 优先于旧飞书凭据，不依赖删除 key 或不存在的 gateway.json。

目标 nginx 为 `/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf`，保留 80→HTTPS 跳转、证书与原头配置。维护门只注入**包含 127.0.0.1:8787 proxy 的 443 server 的 location /**，不能误选 80 的 redirect location。该门使用 `/www/wwwroot/p-acme/core-maintenance.flag`，返回 503 与内部静态维护页；HTTP 跳转后同样进入维护页。SSE 关闭 proxy buffering。修改后先 nginx -t 再 reload。布局变成非预期或维护标记与 gate 不符时拒绝继续。

快照保存在 `/root/zhiming-core-backups/<timestamp>-<sha>/source`。所有 SQLite `*.db` 使用只读连接及 backup API 固定一致性，包括 web.db 和 reports.db，并去掉复制快照的 WAL/SHM；不使用 live 文件简单复制作为数据库验收依据。freeze.json 记录固定 commit、源哈希和已禁用 job ID。install 必须重新校验快照哈希，拒绝修改过的输入。

```bash
"$CORE_PY" tools/deploy_core.py freeze --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --acceptance /protected/acceptance.json --legacy-job-ids /protected/legacy-job-ids.json
"$CORE_PY" tools/deploy_core.py install --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --acceptance /protected/acceptance.json --legacy-job-ids /protected/legacy-job-ids.json --source-snapshot <freeze返回的source_snapshot> --bindings /protected/bindings.json --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env --migration-env-file /protected/core-migrate-live.env
```

install 向专用 live DB 迁移，设置 checkpoint 及运行授权，备份并安装 systemd units，只启动维护门内的新网站。网站用一个 Uvicorn worker、数据库池 4；计算通过专用 charts Python。飞书是独立 `zhiming-core-feishu.service`，报告是独立 `zhiming-core-reports.service/.timer`，每个上海时区分钟检查原计划与 outbox。迁移后核对新 PG 的主体、原话、事实、撤销、附件、事项与报告元数据及旧 sent/uncertain 阻断状态；API 只读检查和浏览器登录不发送模型或渠道测试请求。

最终确认后发布：

```bash
"$CORE_PY" tools/deploy_core.py publish --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --acceptance /protected/acceptance.json --legacy-job-ids /protected/legacy-job-ids.json --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env
```

publish 要求旧 writer 已停、web WorkingDirectory 指向该 SHA、维护门仍闭合、授权 `/api/health` 确认 core3.0/PostgreSQL/LangGraph；然后启用唯一新飞书 gateway 与新报告 timer，确认 active 并移除维护 flag。系统只在原上海时刻发送正常业务报告：晨报 07:00、周日周报 20:00、每月 1 日月报 09:00、1/4/7/10 月 1 日季报 10:00，提前 15 分钟准备。不会因为发布而额外发一次报告。

## 维护回退与恢复

发生上线异常立即运行 maintenance，保持公开 503，停止新 web/gateway/reports service 与 timer，导出最新 live PG custom dump 和最新 body-free 撤销账本到 0600 受保护备份目录。脚本不恢复旧 SQLite/JSON 权威，不重启旧 Hermes Feishu 或旧解释循环。维护期间用户读到静态维护页，不能写入和投递。

```bash
"$CORE_PY" tools/deploy_core.py maintenance --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env
```

修复以最新 live PG 为权威，在新的固定 SHA 和 stage 重验后按发布门恢复。若必须从旧备份恢复数据库，先重放最新撤销账本及后续有效变更，再允许读取、生成和投递；仅恢复旧备份而跳过撤销会造成已删除内容复活，因此维护脚本没有自动旧库回滚。发送中断或 timeout 的 outbox 保持 DELIVERY_UNCERTAIN，只有核对真实 message_id 或提供明确未送达证据后才能对账；禁止重建 business ID 或任意重发按钮绕过账本。
