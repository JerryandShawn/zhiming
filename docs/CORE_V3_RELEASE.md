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

真实模型样本与四流程对照均保留首次失败、单次语义修复和全部物理调用。新 Core 对照遇到已记录的网络、HTTP 429/5xx 或结构化传输故障时，最多恢复两次同一 run/operation；恢复通过正式 PostgreSQL 重试入口，调用数不重置，仍受 standard/deep 总预算约束。认证、配置、输出契约与引用校验失败不使用技术恢复。错误诊断只记录固定类别、HTTP 状态和 usage，不保存供应商原始错误正文。旧流程的隔离词法回退不等同于生产向量环境；缺失依赖或只读工具失败保留在比较结果，不视为新 Core 的质量证明。

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

`freeze` 先安装 nginx 维护门，再停旧报告 service/timer，备份 Hermes config/cron 并仅设置 `platforms.feishu.enabled=false` 与 4 个已核对任务的 enabled=false。首次冻结在制作数据快照前备份并退役旧技能 Python 入口，安装维护门下拒绝执行的新 wrapper；随后核验 Hermes 的进程组终止配置，重启以清理旧子进程并刷新技能缓存，再停旧网站。其他渠道配置保留。此显式 false 优先于旧飞书凭据，不依赖删除 key 或不存在的 gateway.json。

目标 nginx 为 `/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf`，保留 80→HTTPS 跳转、证书与原头配置。维护门只注入**包含 127.0.0.1:8787 proxy 的 443 server 的 location /**，不能误选 80 的 redirect location。该门使用 `/www/wwwroot/p-acme/core-maintenance.flag`，返回 503 与内部静态维护页；HTTP 跳转后同样进入维护页。SSE 关闭 proxy buffering。修改后先 nginx -t 再 reload。布局变成非预期或维护标记与 gate 不符时拒绝继续。

快照保存在 `/root/zhiming-core-backups/<timestamp>-<sha>/source`。所有 SQLite `*.db` 使用只读连接及 backup API 固定一致性，包括 web.db 和 reports.db，并去掉复制快照的 WAL/SHM；不使用 live 文件简单复制作为数据库验收依据。旧 Feishu 连接停止后，另以 backup API 冻结 `/root/.hermes/state.db` 为同目录下的 `hermes-state.db`。freeze.json 记录固定 commit、两类源哈希和已禁用 job ID。install 必须重新校验快照哈希，拒绝修改过的输入。

```bash
"$CORE_PY" tools/deploy_core.py freeze --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --acceptance /protected/acceptance.json --legacy-job-ids /protected/legacy-job-ids.json
"$CORE_PY" tools/deploy_core.py install --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --acceptance /protected/acceptance.json --legacy-job-ids /protected/legacy-job-ids.json --source-snapshot <freeze返回的source_snapshot> --bindings /protected/bindings.json --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env --migration-env-file /protected/core-migrate-live.env
```

install 向专用 live DB 迁移，再通过同一 HermesChannelAdapter 导入最终 Hermes 快照中的受信作者、有效私聊用户原话。它仅使用显式 `feishu/user` 绑定，不导入助手解释、群聊、其他人或失效消息，不提取事实、不调用模型、不投递。重复同步必须新增 0、事实数不变，统计保存在 0600 的 `final-hermes-migration.json`。迁移 owner 随后调用 `ReportScheduleService(repo).seed_defaults('primary')`，仅为已迁 pipeline 且任务/投递目标双重受信绑定的缺失计划建立默认项，保留原暂停设置和既有 schedule；GET 不负责 seed，未配置情况保持未配置。统计只含 created/existing/unconfigured 计数。随后设置 checkpoint 及运行授权，备份并安装 systemd units，只启动维护门内的新网站。网站用一个 Uvicorn worker、数据库池 4；计算通过专用 charts Python。飞书是独立 `zhiming-core-feishu.service`，报告是独立 `zhiming-core-reports.service/.timer`，每个上海时区分钟检查原计划与 outbox。迁移后核对新 PG 的主体、原话、事实、撤销、附件、事项与报告元数据及旧 sent/uncertain 阻断状态；API 只读检查和浏览器登录不发送模型或渠道测试请求。

首次 freeze 固定安装 `/root/.hermes/skills/zhiming`：只把该技能的旧 SKILL.md、顶层 Python 源码及旧安装清单备份至本次 freeze 目录的 `hermes-skill`，逐文件哈希记录；install 复用同一原始备份并再次核验，重复执行不覆盖原备份。该目录中私密 JSON/SQLite、其他技能和 Hermes 会话不变。新 SKILL.md 来自固定 release；`python3 core_consultation.py` 是薄 wrapper，先检查维护门，再取得共享写入锁并重新检查维护门，读取与新服务相同顺序的受保护 0600 环境文件后，用 `os.execv` 执行固定 Core Python 和 release CLI。锁描述符跨 exec 保留，覆盖 CLI 整个执行期；原参数逐项传递，不嵌入凭据、不调用 shell。旧 Python 入口全部替换为 fail-closed 退役提示，不能继续写旧档案或运行第二次解释。安装后再次重启 Hermes 刷新技能缓存，并复核旧 Feishu 显式禁用，再启动新 Web。publish 会核对 SKILL、wrapper、全部退役 stub、原备份和固定 commit manifest；未知新增 Python 入口、修改或错误 env 顺序均阻断发布。维护恢复不还原旧技能及旧解释循环。

最终确认后发布：

```bash
"$CORE_PY" tools/deploy_core.py publish --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --acceptance /protected/acceptance.json --legacy-job-ids /protected/legacy-job-ids.json --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env
```

publish 要求旧 writer 已停、web WorkingDirectory 指向该 SHA、维护门仍闭合、授权 `/api/health` 确认 core3.0/PostgreSQL/LangGraph；然后启用唯一新飞书 gateway 与新报告 timer，确认 active 并移除维护 flag。系统只在原上海时刻发送正常业务报告：晨报 07:00、周日周报 20:00、每月 1 日月报 09:00、1/4/7/10 月 1 日季报 10:00，提前 15 分钟准备。不会因为发布而额外发一次报告。

## 当前原话与保存授权

保存授权仅识别当前明确的保存指令；“已经记录的牌”、查询旧资料、引述指令、疑问和更正意图不授权新增长期事实。明确拒绝保存优先，已有低敏偏好设置及单事实更正的原授权范围继续适用。

当前用户原话中的背景可作为本轮临时引用，不创建或确认长期事实，不更新出生资料。引用保留原话范围、人物、所选事项及原话 revision，结果显示“本轮原话（未保存为长期记忆）”；运行依赖原话版本，不生成虚构事实依赖。旧迁移消息、助手或工具输出、系统报告及未标记来源默认不能进入此通道；渠道只在核验当前发言者后标记可信来源。下一条消息不继承该临时引用，撤销原话或相应来源范围后不能重新引用。

## 删除传播验收

发布前另验证实时塔罗删除的来源传播：同 owner 的牌阵、解释版本、关联执行结果、缓存、待投递正文及各 retry_epoch checkpoint 一起清理；模型迟返回后再次清理 checkpoint。已送达或情况不明的收据仅保留无正文状态，不声称撤回。专属抽牌问题与生成式解读原话写入正式撤销账本，独立聊天原话、被引用的全局事实及后续独立事项修改保留。自动事项中仅由已撤销问题派生的标题与目标清空，事项 ID 与独立事件保留。稳定抽牌与解读键保留墓碑，备份恢复仍须重放最新撤销。

## 报告设置页面

“档案与工具 → 报告设置”以及报告存档页入口均可调整既有四类报告。晨报配置时间，周报另配置 ISO 星期，月报与季报另配置 1 至 28 日或月末；季报仍只在 1、4、7、10 月发送。页面显示北京时间、提前 15 分钟准备和实际下一期时刻，跨午夜时明确显示两个日期。启停不创建新渠道、任务或收件人。

`GET /api/reports/schedules` 仅读取。`PATCH /api/reports/schedules` 必须携带稳定 request_id 和 expected_revision，由服务器解析 owner 并核验既有任务及收件绑定。时间策略进入 PostgreSQL 依赖版本；改期使旧待发送结果失效。投递中修改返回 409，送达待确认和已发送收据不能通过修改日期规避同日、ISO 周、月或季的保护。已经过去的发送时间从后续期次生效；重复请求与同值保存不刷新生效时刻。网络失联重试保留请求 ID，409 保留草稿并要求显式读取新版本；仅真实保存回执允许显示成功。

## 维护回退与恢复

发生上线异常立即运行 maintenance，先设置公开维护门、停止并禁用新 web/gateway/reports service 与 timer，再检查固定源码完整性；源码损坏不会阻止先停写。同时取得技能写入排他锁，等待已启动 CLI 排空；排他锁持续覆盖最新撤销账本、live PG custom dump 及回执写入。等待超时保持维护门关闭且不宣称备份完成。正常情况下导出最新 live PG custom dump 和 `withdrawals-latest.json` 到 0600 受保护备份目录，maintenance.json 保存二者 SHA256 与服务、技能写入排空状态。撤销导出包含每 owner 可直接交给 `repo.apply_privacy` 的正式账本、无正文塔罗请求墓碑与已删 draw ID、已送达及送达不明的无正文投递收据。脚本不恢复旧 SQLite/JSON 权威，不重启旧 Hermes Feishu 或旧解释循环。维护期间用户读到静态维护页，不能写入和投递。若完整性检查失败，写入仍已暂停，需人工在受保护目录完成最新备份后修复。

```bash
"$CORE_PY" tools/deploy_core.py maintenance --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env
```

修复以最新 live PG 为权威，在新的固定 SHA 和 stage 重验后按发布门恢复。优先恢复最新 custom dump；脚本没有自动旧库回滚。若必须人工使用更旧的 PG 备份，保持维护门和全部新旧写入口停止，先完成以下最新撤销重放，再补回之后的其他有效变更、重新核对授权及 schema/checkpoint 权限，最后按新 SHA 的完整验收门恢复。

```bash
"$CORE_PY" tools/deploy_core.py restore-withdrawals --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --withdrawals <maintenance返回目录>/withdrawals-latest.json --legacy-job-ids /protected/legacy-job-ids.json --env-file /etc/systemd/system/mingjingtai.env --env-file /root/.hermes/.env --env-file /protected/core-live.env --migration-env-file /protected/core-migrate-live.env
```

此命令核验维护门、旧 Feishu/报告已禁用、全部 Core writer 已停止、备份文件权限和哈希；取得技能写入排他锁、排空已有 CLI 后，持续持锁到撤销重放及回执完成。锁忙时不加载数据库环境、不执行重放。仅向明确的 live PG 重放。塔罗请求墓碑的旧结果 ID 已清空时，先从恢复库中相同 owner/operation/key/fingerprint 的旧请求解析原 draw/reading ID，实际清除牌堆、解释及关联 run/checkpoint，再写空结果墓碑；不能只把请求设为 deleted 而留下可按 draw ID 读取的牌阵。HTTP 删除的无正文 deleted_ids 也同时保留。已 sent 的收据阻断重复发送，旧 sending 在导出时成为 uncertain，恢复后绝不自动重试。该路径有真实 PostgreSQL `pg_dump`/`pg_restore` 回归，验证旧备份内容曾恢复、重放后已撤销原话/牌阵无法读取或按旧 key 再生、checkpoint 清除及投递收据保持；测试全为合成资料，外部发送为 0。

发送中断或 timeout 的 outbox 保持 DELIVERY_UNCERTAIN，只有核对真实 message_id 或提供明确未送达证据后才能对账；禁止重建 business ID 或任意重发按钮绕过账本。
