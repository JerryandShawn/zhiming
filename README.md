# 知命明镜台

GitHub 私有仓库：[JerryandShawn/zhiming](https://github.com/JerryandShawn/zhiming)。云端开发与环境配置见 [docs/CLOUD_DEVELOPMENT.md](docs/CLOUD_DEVELOPMENT.md)。`main` 保存当前可运行的 v6 网站；`work/core-v3` 保留未接入主站的领域内核重构，不能作为已完成的新运行时发布。仓库不包含真实用户数据库、服务器口令、模型密钥和个人备份。

明镜台沿用 FastAPI、SQLite、原生网页与现有 Hermes 渠道运行时。网站使用自己的 `ChatAgent`，在同一聊天时间线中读取有效记忆、跟进现实事项，并按需调用八字、紫微、西洋星盘或塔罗。白话建议在前，专业依据在末尾折叠；象征解释不作为现实事实或事件概率。

本说明对应 2026-10-10 的 v6 本地实现。生产尚未部署；真实模型评测正在独立进行，真实飞书与定时投递未完成联调；浏览器工具受阻，未取得本轮真实页面截图。自动测试与这些验收项分别记录，不能互相替代。变更记录见 [CHANGELOG-2026-10-10.md](CHANGELOG-2026-10-10.md)。

## 为什么重构记忆

`tests/replay_before_v6.py` 以旧 `ChatAgent` 路径截获发给模型的请求，不连接模型。合成样本有 601 条消息，其中最早一条包含“不能上夜班”的现实约束；实际近期消息只注入 32 条，检索仅使用本轮短句，截获请求没有该约束，也没有事项状态。结果位于受忽略保护的 `private/v6-before/replay.json`。这证明该回放在组装阶段漏掉关键依据，不能据此断言所有模型回答都会遗忘。

另一个根因是“共享解释规范”被误当作“共享当前事实”：网站、Hermes 与报告此前没有统一的事实版本和渠道绑定边界。仅调整提示词不能保证更正立即生效，也无法保证模型说“已记住”时已经写入数据库。v6 把身份、原话、状态、版本与保存回执放到程序层，语义检索只辅助补充背景。

## 调用链与数据边界

网站调用链：`static/app.js → POST /api/chat → main.auth / owner_services → ConversationStore.begin → ChatAgent.run → v6_agent.run → StateStore + ContextBuilder → 按需工具 → final_answer 校验 → revision 检查 → ConversationStore.finish → SSE result`。流式阶段显示处理状态；最终结论通过结构、引用、牌位和版本检查后才展示。

Hermes 调用链：已绑定渠道 → `context_query.ChannelContext` → 只读核验 Hermes 原始消息库 → 同一个 `StateStore` 与 `ContextBuilder` → Hermes 模型运行 → 校验 CLI。网站强制执行自己的最终提交校验；Hermes 自由聊天是否实际调用适配器仍需渠道联调，技能说明本身不等于强制执行。

报告调用链：显式 `report` 渠道绑定 → `chart_context.py` 或 `context_query.py` 准备上下文并返回 `run_id/revision` → Hermes 生成结构化 JSON → `report_store.py` 校验身份、当前版本、日期和真实字段 → 原子归档 → `report_pipeline.py` 队列按原时刻投递。模型调用不占用数据库写事务。

| 标识 | 实际含义与边界 |
| --- | --- |
| `owner_user_id` | 数据归属。网站由口令映射，渠道由服务端绑定解析，不接受模型或客户端自行指定 owner。 |
| `subject_id` | 本人 `self` 或该 owner 明确创建的人物。事实、消息、事项、抽牌和上下文均保留人物范围。 |
| `conversation_id/session_id` | 用户看到的持续交流时间线；默认 `shared`。不是无限拼入模型的全部历史。 |
| `case_id` | 一个现实问题及其目标、约束、决定、行动、结果。页面手动选择单个事项；同一聊天可按多个既有事项标题自然关联，`POST /api/chat` 的 `case_ids` 可显式传入最多 8 个同 owner、同人物的事项，无需另建聊天。指代不明确时返回澄清状态。 |
| `run_id` | 一次可追溯执行。记录版本、召回 ID、注入 ID、排除原因、预算和验证状态，不保存隐藏思维链。 |
| `revision` | owner 当前资料版本。更正、事件及原始消息登记后推进；过期生成结果不能覆盖新状态。 |

| 文件或数据 | 权威内容 |
| --- | --- |
| `state.sqlite` / `hermes/state_store.py` | owner、人物、渠道绑定、原始来源、有效事实、事项、事件、删除标记、迁移映射与最小 trace。 |
| `web.db` / `hermes/conversation_store.py` | 网站聊天时间线、请求状态与图片引用。旧记忆表不再作为 v6 事实写入口。 |
| `tarot.db` / `hermes/tarot_store.py` | 已保存洗牌、牌阵、选择、翻牌状态、解读版本与幂等请求。 |
| `retrieval.db` / `hermes/semantic_index.py` | 可重建的本地语义索引，不能覆盖事实主库。 |
| `archive.json`、`reports.db` | 既有归档与报告投递队列。旧派生内容不自动升级为用户事实。 |

当前主账号保留原网站目录；其他 owner 的网站历史与检索目录由 `owner_services()` 隔离。共享状态和塔罗数据库在每次读写时按 owner 限定。旧 `archive.json` 的读取限于明确配置的原账号，撤销资料会阻止使用无来源的旧派生档案兜底。

## 每轮上下文与事实写入

`ContextBuilder.build()` 先解析人物与事项，再从主库读取当前有效事实。约束、偏好、更正、档案和目标优先进入上下文；其次补充相关事实、经过人物/来源过滤的检索结果与近期原话。简短指代会结合近期用户原话和事项标题检索，不仅搜索孤立的一句“后来呢”。索引中的记忆命中必须回查当前有效 snapshot，过期或撤销记录不能因索引尚未更新而重新生效。

例如同一条消息提到“学习安排”和“工作安排”，`StateStore.resolve_cases()` 可关联这两个既有事项，`import_message()` 幂等追加原始消息的事项关联；`v6_agent.run()` 保留这些关联，不因缺少单一 `case_id` 再创建第三个事项。多个事项并行时，`record_case_event` 必须指定本轮已关联的目标 `case_id`，自动决定提取也不会把同一决定写入所有事项。自然关联依赖可识别的事项标题与现有范围，不能据此承诺任意隐含指代都能自动消歧；页面目前没有多选控件。

预算由 `ZHIMING_CONTEXT_TOKENS` 与 `ZHIMING_REPLY_RESERVE` 控制，默认分别为 64000 与 18000。UTF-8 字节数除以 2 是保守估算，模型响应的实际 usage 另行记录。关键事实自身超过预算时明确失败，不截断关键字段；历史和非关键召回可按预算减少。工具调用前还会检查最终请求预算。

模型通过 `remember_fact` 提出逐字引用的候选，`store_candidate()` 和 `StateStore.put_fact()` 检查作者、人物、来源范围、授权、时间和版本。保存成功返回 `write_status=saved`；待确认、错误与未配置状态不返回保存成功。出生字段使用排盘真正读取的 `birth.solar_datetime`、`birth.location.lng/lat`、`birth.timezone_offset` 等规范路径。

更正必须有新原话、明确替代关系及当前 revision。接口把原始消息登记与更正放入同一事务，避免登记来源时推进版本造成请求与自己冲突。补记旧事不能替代较新的当前事实；多个相互冲突的出生字段不会简单取最后写入值。

停止使用与删除会写入 suppression/tombstone，撤销相关事实、事项派生内容、检索和塔罗上下文。后续导入先检查这些标记。`scope=fact` 保留原始聊天供用户查看，但排除其作为后续依据；`scope=source` 同时清除关联原始内容。上下文也排除已撤销来源的同轮助手复述及可识别的派生依赖。审计保留标识和操作，不复制被删除正文。

`StateStore.record_trace()` 默认保留 30 天运行元数据，`ZHIMING_TRACE_RETENTION_DAYS` 可设为 1–3650 天。清理发生在该 owner 写入新 trace 时，只清理该 owner 超期记录；这是按写入触发的保留策略，不是每天自动巡检，长期不活跃 owner 的旧 trace 不会在第 30 天由独立任务自动删除。trace 采用字段白名单和正文/凭据/隐藏推理过滤，不替代其他服务日志、备份和模型提供方的保留配置。

## 输出与塔罗工作流

`guidance.workflow()` 区分普通交流、更正、决策、支持、三盘、塔罗与报告；`mode_schema()` 只要求当前模式需要的字段。普通问候无需凑成长报告。三盘/塔罗贡献可以缺失、无关、未使用或不确定；实际采用的字段必须有已注册的 `ref/path/value`，不能为了覆盖体系虚构共同主题。

`#/tarot` 与主聊天、`#/memory` 共享 owner、人物和事项。默认是一个问题输入框与三张“梳理问题”；高级区提供背景、正逆位、点选或实体牌录入。`focus1`、`reflect3`、`choice5` 分别为单张、三张和 A/B 五张牌阵，A/B 含义在抽牌前冻结。

`TarotDrawService` 使用 `secrets.randbelow` 和 Fisher–Yates 洗牌，方向独立等概率产生，默认启用正逆位。完整牌序和方向只保存在服务端。点选返回 opaque 牌背 ID，选择原子且幂等；未翻牌不会泄露牌面。刷新或模型重试恢复原 draw，同一事项阶段默认复用已有结果，只有明确新一轮才建立关联新记录。

draw 冻结问题、选项、人物、事项、牌库/牌意/方法/牌阵版本及上下文快照。`TarotReadingVersion` 单独记录模型、提示版本、上下文和 `running/success/failed`；补充信息或重新解释不会改牌。手动更正建立新 revision，隐私删除优先清除相应内容。未配置 AI 时仍可抽牌、录入和阅读静态牌意，AI 解读明确失败。启动恢复中断 reading，不将它标为成功。

完整 78 张牌、中文正逆主题、误读与问题见 `hermes/tarot_deck.py`；原创 SVG、统一牌背与许可证见 `static/tarot/`、`static/tarot/licenses.json`。编号采用 RWS 顺序，其中力量 8、正义 11；图片为产品自制图形牌。随机结果和结构校验都不证明占卜预测有效。

## API 概览

所有业务接口沿用 `X-Token` 鉴权。

| 路由 | 用途 |
| --- | --- |
| `GET /api/state`、`PATCH /api/state/settings` | 当前人物事实、事项、版本与设置。 |
| `GET /api/memories`、`PATCH/DELETE /api/memories/{id}` | 读取、更正、停用及按范围删除。 |
| `GET /api/memories/{id}/source`、`/audit` | 可核验原话与不含删除正文的变更记录。 |
| `GET/POST /api/cases`、`PATCH /api/cases/{id}`、`POST /api/cases/{id}/events` | 事项及明确的决定、执行、反馈。 |
| `POST /api/chat`、`GET /api/chat/{id}`、`POST /api/chat/{id}/cancel` | 同一 ChatAgent、请求恢复与取消。 |
| `GET /api/tarot/deck`、`GET/POST /api/tarot/draws` | 完整牌库、历史与保存新牌阵。 |
| `GET/DELETE /api/tarot/draws/{id}` | 恢复或删除牌阵及关联内容。 |
| `POST /api/tarot/draws/{id}/select`、`/reveal`、`/cancel` | 选牌、翻牌及取消。 |
| `PATCH /api/tarot/draws/{id}/manual` | 实体牌显式修订。 |
| `GET/POST /api/tarot/draws/{id}/readings` | 解读版本与经过校验的 SSE 结果。 |
| `GET /api/chart`、`/api/chart_ziwei`、`/api/chart_astro` | 既有确定性排盘。 |
| `GET /api/reports/status`、`POST /api/reports/{id}/retry` | 原报告队列状态与受限重试。 |

## 环境与依赖

本轮本地 API 测试使用 Python 3.12 环境 `.venv312`；SQLite 属于 Python 标准库。本地基础 Web 版本为 `fastapi==0.115.12`、`uvicorn==0.34.3`、`httpx==0.28.1`、`Pillow==11.3.0`。2026-10-11 另以只读 `importlib.metadata` 核对生产 Linux CPython 3.11.6：Web 使用 FastAPI 0.141.1、Uvicorn 0.52.1、HTTPX 0.28.1、Pydantic 2.13.4、Starlette 1.6.0；排盘使用 lunar-python 1.4.8、py-iztro 0.1.5、pythonmonkey 1.1.0、pyswisseph 2.10.3.2。

`requirements.txt` 引用 `requirements-web.lock`，包含 Web、图像与本地向量索引的已安装依赖闭包；`requirements-charts.lock` 单独固定排盘环境及 pythonmonkey 所需依赖。这两个文件是现有 Linux 环境的版本快照，尚未验证从空环境重新安装，也没有 wheel 哈希。不要把两个锁文件合装：py-iztro 0.1.5 固定要求 Pydantic 2.10.6，与 Web 的 2.13.4 不同。通过 `CHART_PYTHON` 指向独立排盘解释器，不能覆盖网站环境的 Pydantic。

本地向量索引还需要真实 MiniLM 模型文件；三盘解释器需能导入 `lunar_python`、`py_iztro`、`swisseph`。基础 API 可以启动，不意味着这些模型或计算环境已可用。锁文件针对已核对的 Linux/Python 环境，不宣称覆盖 Windows 或其他 Python 版本；测试目录中的临时依赖不作为生产配置。

前端依赖由 `package.json` 和 `package-lock.json` 管理；`npm ci` 安装锁定版本，`npm run build` 构建本地样式，不依赖运行时 CDN。本轮没有引入第二套大型 Agent 框架。

| 环境变量 | 作用 |
| --- | --- |
| `ZHIMING_BASE` | 状态、网站历史、塔罗与归档所在目录。所有入口应使用同一约定。 |
| `ZHIMING_SKILL` | Hermes 领域模块目录；本地通常为仓库 `hermes`。 |
| `MINGJING_TOKEN`、`MINGJING_OWNER_ID` | 现有主账号口令及 owner ID；口令从受保护配置加载，不写入仓库。 |
| `ZHIMING_TOKEN_OWNERS` | 其他口令到 owner 的 JSON 映射；同样属于受保护配置。 |
| `KIMI_API_KEY` 或 `MOONSHOT_API_KEY` | 模型服务凭据，仅服务端使用。 |
| `KIMI_BASE_URL`、`KIMI_MODEL` | 现有兼容模型入口及模型名；代码默认模型为 `kimi-k3`，实际可用性须联调。 |
| `HERMES_DB` | Hermes 原始消息数据库，适配器只读并校验真实作者。 |
| `ZHIMING_CHANNEL`、`ZHIMING_EXTERNAL_ID` | CLI 当前显式绑定渠道身份，不能按同名猜测。 |
| `ZHIMING_LEGACY_OWNER` | CLI 允许读取旧归档的明确 owner，不能通配其他账号。 |
| `ZHIMING_EMBEDDING_MODEL` | 本地向量模型目录。 |
| `CHART_PYTHON` | 已安装三盘计算依赖的 Python 解释器。 |
| `ZHIMING_CONTEXT_TOKENS`、`ZHIMING_REPLY_RESERVE` | 输入预算与回答预留，须与实际模型限制匹配。 |
| `ZHIMING_TRACE_RETENTION_DAYS` | trace 默认 30 天，允许 1–3650 天；该 owner 下次写入 trace 时清理过期记录。 |

在已有 Python 环境和受保护环境变量加载完成后，于仓库根目录启动本地服务：

```powershell
$env:ZHIMING_BASE = Join-Path (Get-Location) 'private/local-v6'
$env:ZHIMING_SKILL = Join-Path (Get-Location) 'hermes'
.venv312/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

不要把本地空数据目录指向生产库试跑。`MINGJING_TOKEN` 未配置时接口返回 503；缺少模型凭据只影响 AI 生成，不能伪装成静态模板成功。当前实现按单个网站 worker 管理活跃请求；没有多 worker 的分布式任务协调配置。

## 迁移与渠道绑定

先停止相关写入并制作一致备份：网站数据库与图片、归档、状态库、塔罗库、报告队列、Hermes 原始消息库和 cron 配置应分别保留。凭据由原受保护配置保管，不复制到交付文档。生产迁移本轮尚未执行。

`migration_state.py` 默认 dry-run，不会创建目标数据库或更改旧数据。先在备份副本运行：

```text
python migration_state.py --source <旧数据副本目录> --destination <新状态目录> --owner <明确的owner>
python migration_state.py --source <旧数据副本目录> --destination <新状态目录> --owner <明确的owner> --bindings <受保护的绑定JSON文件> --apply
```

绑定文件为 `[{"channel":"feishu","external_id":"<实际渠道用户ID>"},{"channel":"report","external_id":"<既有任务标识>"}]`。示例没有真实身份或凭据。绑定必须来自实际账号/渠道配置，不能由模型补全；用同一个 owner 关联网站、飞书和其报告任务。

迁移先重放旧删除/停用，再导入原话和 ID 映射。能逐字对应真实用户消息的旧记忆才保留为用户陈述；助手总结、来源不明档案标为 `legacy_unverified`，超长旧段落只保留来源而不截成事实。重复运行使用 `legacy_map` 续接，不重复提升来源不明内容。对比返回的消息、核验记忆、未核验内容、跳过映射和错误条目后，再在隔离环境检查典型事项。

绑定后的 CLI 示例：

```text
python hermes/context_query.py --base <数据目录> --channel feishu --external-id <已绑定ID> --query "上次讨论的安排现在怎样了" --sync-hermes
python hermes/chart_context.py --base <数据目录> --channel report --external-id <已绑定任务ID> --date YYYY-MM-DD
python hermes/report_store.py --base <数据目录> --channel report --external-id <已绑定任务ID> --run-id <准备阶段返回值> --date YYYY-MM-DD --type 晨报 --structured <报告JSON> --archive <该owner归档路径>
```

`remember-message-id` 必须指向该绑定身份在 Hermes 数据库里的有效用户消息；适配器不接受伪造作者或助手回答。更正需带准备阶段取得的 `--revision`。CLI 重新注册本轮来源，不能把网站上一轮的检索 ref 原样搬入报告。`guidance.py --validate` 是解释结构工具，不替代绑定身份和版本校验的 `context_query.py`/`report_store.py` 路径。

## 隐私撤销导出与离线恢复

从旧备份恢复 v6 时，需要把备份之后发生的停止使用、删除和塔罗请求撤销重新应用到恢复副本。`hermes/privacy_replay.py` 提供两个显式操作，不能与 `migration_state.py` 的 dry-run 混用；它没有隐含的恢复目标，也没有自动发布服务的行为。

先从最新有效数据导出指定 owner 的撤销记录。导出只读两库，只写一个此前不存在的新文件；已有输出文件会被拒绝。在 POSIX 系统上输出权限设为 0600。文件包含 owner、来源/事实标识、操作和塔罗重试键哈希，不包含用户正文、问题快照、原文 quote 或明文重试键。它仍是敏感的内部标识文件，须放在受保护位置，不能加入发布包。

```text
python hermes/privacy_replay.py --export --owner <owner> --state-db <当前数据目录>/state.sqlite --tarot-db <当前数据目录>/tarot.db --file <受保护目录>/revocations.json
python hermes/privacy_replay.py --apply --owner <同一owner> --restore-state-db <离线恢复目录>/state.sqlite --restore-tarot-db <离线恢复目录>/tarot.db --file <受保护目录>/revocations.json
```

导出应在停写窗口或一致备份副本上进行，确保覆盖切换前的最新撤销。多 owner 需分别导出并应用；输入为受信任操作员文件，不能接受模型或普通用户上传的撤销文档。CLI 会核对 owner、格式、表结构和目标已存在，但不能证明所给路径已经离线，也不会识别某个路径是否属于生产。应用前必须人工核对两库来自同一恢复集、与在线库路径不同，且所有相关写入进程已停止。

`--apply` 只改显式指定的 `state.sqlite` 和 `tarot.db`，通过 SQLite ATTACH 的单个事务重放撤销；失败时回滚两库。为保证多库恢复的事务边界，任一目标使用 WAL 时直接拒绝，不自动 checkpoint、不切换 journal mode。先在离线副本中按照备份流程生成并核验 rollback-journal 目标，不能为了通过检查而删除 `-wal`/`-shm` 文件。该限制只针对隐私重放目标，不改变现有在线库配置。

重放会保留删除强度：已删除项不会降级为停用；按 scope 清除事实正文或原始消息，撤销相关事项/事件，并清除该 owner 的旧 trace。涉及撤销来源或已失效重试键的恢复 draw 连同 reading 被删除，原重试键不能重新创建它。旧塔罗 tombstone 无法区分“删牌阵”和“仅撤销上下文”，因此离线恢复采取保守方式，可能删除原本只需清空上下文的相关牌阵；应在恢复验收中核对数量，而不是承诺恢复所有原牌阵。

此工具**不处理**外部 `web.db`、`webchat.json`、`archive.json`、`retrieval.db`、报告队列或已导出的报告文件。两库返回 `applied=true` 只说明两库事务完成，不能宣称整个部署已经完成隐私恢复。恢复流程必须在开放网站、渠道、报告 worker 和重建索引之前，按同一撤销记录处理这些外部副本：`scope=fact` 可保留原话供用户查看但禁止注入模型；`scope=source` 应清除相应原文和派生副本；重新生成索引与可重建缓存，无法核验来源的旧摘要/报告继续隔离。外部清理与重建当前属于审阅恢复流程，没有一键自动覆盖所有存储的工具。

CLI 返回撤销、清除、失效记录数量及新 revision。应检查 owner 隔离、事实不可再导入、draw/reading 不可恢复、旧请求键被拒绝，并再次执行确认幂等。自动回归见 `tests/test_privacy_v6.py`；生产备份恢复尚未执行，离线 fixture 结果不能替代生产恢复验收。

## 报告时刻与发布注意事项

现有代码配置按 Asia/Shanghai 保持以下时刻；v6 不新增提醒，也没有发送测试飞书消息。

| 报告 | 准备 | 投递 |
| --- | --- | --- |
| 晨报 | 每天 06:45 | 每天 07:00 |
| 周报 | 周日 19:45 | 周日 20:00 |
| 月报 | 每月 1 日 08:45 | 每月 1 日 09:00 |
| 季报 | 1/4/7/10 月首日 09:45 | 同日 10:00 |

来源为 `configure_pipeline_v4.py` 和 `report_pipeline.scheduled()`。`mingjingtai-reports.timer` 每分钟检查队列，不是每分钟发送报告。报告日期从 2026-09-30 起必须通过结构化校验；启用共享状态后还需明确 owner/subject 和生成时版本。纯文本补偿仅用于历史报告，不能拿来绕过新报告门槛。

上线前需要把渠道绑定与环境配置接入实际 Hermes 任务，并独立验收准备、归档、到点投递。不要重新执行旧 `configure_cron.py` 来覆盖当前分阶段任务。`deploy.py` 已移除导入即连接和自动覆盖服务的行为；默认或 `--dry-run` 只读本地文件，输出完整清单、大小和 SHA256，覆盖 Hermes Python/SKILL、静态 JS/CJS/CSS/HTML/SVG/JSON、迁移、依赖锁与测试。它不会联网、上传、修改数据库或重启服务。

## 审阅发布步骤

当前脚本没有经验证的生产备份、迁移与原子切换执行器，因此所有 `--apply` 都明确拒绝。缺少 `--release-dir`、`--owner` 或 `--bindings` 时先提示缺少前置项；参数齐全也不会开放生产写入。不要把生成 manifest 或传入 stage 路径解释为发布已验证。

```text
python deploy.py
python deploy.py --dry-run --release-dir <已完成验证的本地隔离stage目录>
```

实际发布需要另行审阅的操作计划，并按下列顺序完成：

1. 从隔离 stage 固定发布内容，运行自动回归和真实模型检查，保存 manifest 与结果。核对生产将安装的每个文件与已验证 stage 的 SHA256 一致；不要从随后继续改动的工作目录上传。
2. 明确唯一 owner 及渠道绑定文件，核验飞书真实用户、人物范围和既有报告任务。没有有效 `--bindings` 文件不得迁移或切换；绑定内容留在受保护位置，不加入清单或日志。
3. 在生产写入前暂停网站写入、Hermes 相关任务和报告 worker。对每个 SQLite 数据库使用 SQLite `.backup` 命令或 `Connection.backup()`，并检查备份的 `PRAGMA integrity_check`；在同一个停写窗口备份归档、图片、配置和代码。已有 v6 数据时另为各 owner 导出最新隐私撤销文件，恢复旧备份必须先重放再处理外部副本。不能只复制正在写入的数据库文件并称为一致备份。
4. 先以备份副本作迁移输入，在隔离目标目录执行 dry-run，再带明确 owner 与 bindings 执行 apply。比对 `source_messages`、`source_memories`、`inactive_first`、`legacy_sections` 和已核验/未核验数量；检查 `errors`、`already_mapped` 与跳过状态。dry-run 不执行完整写入校验，数量有差异须逐项解释，不能直接忽略。确认重复 apply 不增加重复事实，撤销内容不复活。
5. 分别准备 Web 与排盘解释器，按两个锁文件校验依赖和导入，设置 `CHART_PYTHON`。在隔离 stage 验证服务、78 张牌加牌背、恢复 draw、记忆更正与报告身份/版本门槛；记录真实模型、飞书和投递各自的结果。
6. 审阅新旧目录、文件哈希、迁移结果和回滚点后，才使用单独审阅的发布操作切换已验证 release。代码、Hermes 技能、共享数据路径和原报告门槛必须协调切换；首次检查失败立即保持停写并按回滚步骤处理。此仓库当前没有自动执行这一步的脚本。

这些步骤是发布门槛和操作说明，本轮未执行生产备份、迁移、切换或投递。只读依赖 metadata 核对不属于部署。

## 测试与验收边界

本地回归命令：

```powershell
.venv312/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v
node tests/frontend.test.cjs
node tests/dom.test.cjs
npm run build
```

需要计算依赖的测试应在已配置的排盘解释器中执行；跳过依赖不能算排盘通过。`tests/replay_before_v6.py` 是保留的旧链路合成回放脚本，会写 `private/v6-before/replay.json`；它不连接真实模型。`test_vertical_v6.py` 经过真实 FastAPI 路由和 ChatAgent，但模型响应使用 mock。DOM 测试覆盖交互与清理规则，不能代表实际浏览器排版或屏幕阅读器人工验收。

下面使用附件中的 M/T 编号。状态“自动覆盖”表示有可定位的确定性/集成断言；模型是否真正采用事实及真实外部服务效果另行验收。最终执行结果以本轮测试输出为准，不在这里推导预测准确率或长期不遗忘保证。

| 需求 | 文件、函数或路由 | 对应测试与验证范围 |
| --- | --- | --- |
| M01 长对话与重启恢复 | `ContextBuilder.build`、`StateStore.snapshot` | `test_state_v6.test_300_turn_restart_retains_critical_facts_and_case`；`test_vertical_v6.test_300_mixed_rounds_restart_constraints_and_unknowns`，300 轮合成场景自动覆盖。 |
| M02 更正传播 | `domain_api.edit`、`profile_archive`、`ChannelContext.prepare/validate_response`、`TarotDrawService.purge_context` | `test_channels_v6.test_web_hermes_report_share_correction_and_owner_scope`、`test_chart_profile_uses_current_explicit_fact`；`test_vertical_v6.test_deletion_purges_tarot_derived_snapshots`；`test_channel_evidence_v6.test_bound_fact_ref_is_reauthorized_and_coarse_archive_ref_rejected`、`test_retrieved_original_ref_has_live_owner_and_revision_gate`。后两项使用真实引用校验器和合成绑定数据，验证有效 fact/source 引用、拒绝粗粒度 archive 引用与过期 run；真实飞书仍待联调。 |
| M03 事项与人物恢复 | `main.api_chat`、`StateStore.resolve_cases/import_message`、`v6_agent.run/record_case_event`、`main.agent_history/owner_catalog` | `test_state_v6.test_case_a_b_a_and_multiple_subjects`；`test_review_v6.test_history_index_keeps_subject_scope`；`test_multicase_v6.test_explicit_multi_case_message_and_event_target_survive_restart`、`test_natural_multi_case_title_association_and_invalid_ids`。新增两项通过实际聊天路由与 mock 模型检查显式/自然多事项关联、事件只写目标、无多余事项及无效 ID 拒绝；持久化关联有断言，完整重启恢复由前述 StateStore 测试覆盖。页面手选仍为单项，聊天/API 支持多个事项。 |
| M04 时间与历史版本 | `StateStore._facts/put_fact` | `test_state_v6.test_correction_propagates_and_old_time_can_be_read`、`test_old_event_cannot_replace_current_fact`；`test_review_v6.test_expired_memory_cannot_reenter_through_stale_index`。 |
| M05 不把解释当事实 | `store_candidate`、`StateStore._refs/put_fact`、事件门槛 | `test_state_v6.test_no_prediction_or_hypothesis_promotion`、`test_case_execution_requires_user_source_and_idempotence`；`test_review_v6.test_negated_choice_does_not_become_decided_event`。语义泛化需模型评测。 |
| M06 失败与预算 | `ContextBuilder.guard`、`v6_agent.run`、保存回执 | `test_vertical_v6.test_chat_actual_context_and_failed_fact_candidate`、长对话预算断言；`test_review_v6.test_no_write_receipt_rejects_short_saved_claim`。 |
| M07 并发与幂等 | `StateStore.db/_revision`、`report_store.store` | `test_state_v6.test_concurrent_stale_writes_only_one_commits`、`test_nested_write_registration_and_mutation_are_atomic`；`test_channels_v6.test_stale_report_rejected_before_validation_and_during_commit`。 |
| M08 删除、恢复与权限 | suppression/tombstone、`domain_api.purge`、迁移、`privacy_replay.export_privacy/apply_privacy` | `test_state_v6.test_stop_and_delete_block_reimport_and_purge_audit`、`test_later_legacy_delete_is_replayed_before_reimport`；`test_review_v6.test_deleted_fact_does_not_reenter_via_same_turn_assistant`；`test_privacy_v6.test_deleted_fact_draw_and_retry_keys_cannot_resurrect_after_restore`、`test_both_targets_rollback_on_missing_tarot_schema`、`test_cli_export_then_apply_executes_real_restore`。两库 fixture 有断言，外部副本与生产恢复仍需单独验收。 |
| M09 直接/间接采用 | `ContextBuilder.build`、实际 `/api/chat` | `test_channels_v6.test_web_hermes_report_share_correction_and_owner_scope`；`test_vertical_v6.test_chat_actual_context_and_failed_fact_candidate`。注入和 mock 采用有断言，真实模型采用仍须单独报告。 |
| M10 未知信息不编造 | 有效证据集合与输出规则 | `test_vertical_v6.test_300_mixed_rounds_restart_constraints_and_unknowns` 检查未知余额未出现；模型面对未知问题的完整语义表现不由该断言证明。 |
| T01 完整牌库与素材 | `tarot_deck.py`、`static/tarot` | `test_tarot_v6.test_complete_original_editorial_deck`、`test_every_original_asset_exists_and_is_safe_svg`；真实截图未完成。 |
| T02 三阵与三种录入 | `/api/tarot/draws`、`submitTarot` | `test_tarot_v6` 自动、点选、choice 与 manual 用例；`tests/dom.test.cjs` 三种流程、正逆位与 A/B 输入断言。 |
| T03 冻结与随机边界 | `TarotDrawService.create_draw`、Fisher–Yates | `test_unbiased_algorithm_bounds_and_reversals_setting`、`test_choice_options_required_frozen_and_manual_unique`、`test_meaning_snapshot_does_not_change_after_library_edit`。不采用随机频数阈值作为 CI 验收。 |
| T04 恢复与并发点选 | `select/reveal/request_result/recover_running` | `test_pick_back_only_concurrent_double_click_and_refresh`、`test_cancel_and_restart_recover_pending_reading_without_redraw`；DOM 断网重发断言。 |
| T05 解读不改牌 | `begin_reading/finish_reading`、`validate_tarot` | `test_reading_retry_is_separate_and_does_not_redraw`；`test_vertical_v6.test_tarot_wrong_card_blocked_then_repair_same_draw`；错误牌被拒后修复。 |
| T06 真实失败状态 | `POST /readings`、`requestTarotReading` | `test_vertical_v6.test_draw_reload_idempotency_privacy_and_unconfigured_model`；DOM 模拟超时与结果恢复。真实网络故障联调不由 mock 代替。 |
| T07 牌阵关联与反馈 | `continueTarotChat`、`/api/cases/{id}/events` | DOM “第三张是什么意思”携带 draw/case、反馈与 stale revision 断言；`test_vertical_v6.test_cases_current_revision_and_events_distinguish_execution`。 |
| T08 重复请求复用 | `create_draw(explicit_new=...)` | `test_same_case_stage_reuses_including_cancelled_and_new_is_linked`；重复请求不隐式换牌。 |
| T09 牌意非事实 | `StateStore._refs`、`TAROT_RULES`、事项反馈 | 事实来源与事件类型测试、DOM 用户反馈路径；否认牌意后的完整回答语义仍需模型评测。 |
| T10 塔罗独立与可选对照 | `workflow/mode_schema/validate_final` | `test_guidance_v6.test_tarot_does_not_trigger_three_charts_or_birth_requirement`、`test_real_contribution_subset_not_forced_into_three`、`test_one_contribution_is_not_called_consensus`。 |
| T11 可访问性与状态 | `static/index.html`、`static/app.js`、`static/paper.css` | DOM 键盘移动、减动画、状态与折叠依据断言；SVG 完整性自动检查。桌面/移动视觉和真实读屏尚未验收。 |
| T12 权限与恶意输入 | `main.auth`、StateStore、draw owner 查询、输出清理 | `test_tarot_v6.test_owner_scope_on_every_state_path`；`test_vertical_v6.test_two_account_and_two_subject_isolation`；`test_channels_v6.test_unbound_or_spoofed_channel_rejected`；DOM XSS 清理。提示注入的完整模型行为需语义评测。 |
| 原能力回归 | guidance、chart_context、report_pipeline | `test_guidance_v5`、`test_chart_quality_v5`、`test_v4.test_schedule_and_no_early_or_duplicate_delivery`、`test_channels_v6.test_new_reports_cannot_bypass_structured_or_identity_gate`、`tests/frontend.test.cjs`。 |
| 最小审计与保留 | `StateStore.record_trace` | `test_privacy_v6.test_default_and_configured_retention_are_owner_scoped_and_body_free`；默认期限、自定义期限、owner 隔离与正文过滤有断言。 |

## 机制参考与证据边界

以下为 2026-10-11 核对的官方机制说明，上游文档可能继续变化。它们用于说明设计取舍；本项目的实现、部署版本和故障根因仍以本地调用链、代码与可重放测试为依据。

| 官方参考 | 对本项目的用途与边界 |
| --- | --- |
| [Hermes Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) | 官方说明有容量上限的持久记忆、显式写入工具，以及会话开始时注入的冻结快照。冻结快照是 Hermes 上游描述，不等于本站 `ChatAgent` 已实现或采用该机制，更不能单凭官网认定本站遗忘原因；本站 v6 每轮从 StateStore 读取当前有效状态。 |
| [Hermes Sessions](https://hermes-agent.nousresearch.com/docs/user-guide/sessions) | 区分保存的会话/消息、恢复与搜索能力，帮助审查“历史存在”与“本轮已注入”之间的边界。本站旧链路 601 条保存、32 条近期注入的结论来自合成回放，不来自官网，也不要求用户为切换事项另建聊天。 |
| [Anthropic：Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | 参考其有限上下文预算、按轮选择有效信息和长期任务状态管理原则；本项目据此采用关键事实优先、来源回查和预算门槛，效果仍需本项目测试与真实模型验收。 |
| [Python 3.11 secrets](https://docs.python.org/3.11/library/secrets.html) | 说明操作系统随机源和 `randbelow(n)` 的边界，用于服务端 Fisher–Yates 的随机下标与 opaque 牌背标识。该文档不验证本项目洗牌实现，也不证明牌意具有预测效度。 |

## 故障排查与回滚

| 现象 | 检查与处理 |
| --- | --- |
| 409 资料已变化 | 重新读取 `/api/state` 与当前事项，带新 revision 提交；不能删除版本检查来强行覆盖。 |
| 新增记忆未进入向量结果 | 先检查 StateStore 的有效状态与 source；关键事实直接读取，不应等待索引。检索模型故障可独立修复。 |
| “来源已停止使用” | 保留 suppression；如用户确实重新授权，使用新的原话，不复活旧来源 ID。 |
| AI 未配置或超时 | 查看真实 reading 状态，沿用 draw 新建解释版本；不要重抽或改用模板冒充成功。 |
| 抽牌同键参数不同 | 返回错误是预期保护。恢复原请求，或由用户明确发起新问题/新一轮。 |
| 新报告拒收 | 检查结构 JSON、渠道绑定、run_id、日期及 revision；资料变更后重新准备上下文生成。 |
| 页面牌面缺失 | 核对部署包含全部 SVG 与许可证，不能只上传 JS/CSS。 |
| 隐私重放失败或目标为 WAL | 保持离线，核对 owner、两库 schema 与显式恢复路径；用一致备份流程建立 rollback-journal 副本。不要删除 WAL 文件来绕过检查。 |
| 两库恢复成功但历史仍含已删除内容 | 尚未完成外部副本清理。根据 scope 处理网站历史、归档、报告与检索缓存后才能开放服务。 |

当前没有“一键关闭 v6 状态”的运行时开关。安全回滚必须协调应用版本、数据目录、Hermes 技能/任务和报告结构门槛：先停写并备份当前全量数据与删除标记，回切完整的上一代码/配置快照，在隔离副本验证后再恢复服务。恢复 v6 两库时，先从最新有效数据导出撤销，再对离线恢复副本重放，随后独立处理外部网站/归档/报告/检索副本。不要删除 `state.sqlite` 或 `tarot.db` 来回退，也不要用旧备份覆盖用户刚完成的更正或删除。旧版本不理解 v6 撤销标记；仅执行两库重放不能使旧程序自动遵守这些标记，若不能保证全链路过滤生效，应保持维护/只读状态。

模型、飞书、投递、生产迁移与上线是独立验收项。此版本没有“永不遗忘”、预测准确率或临床疗效结论；规则检查证明的是已读取来源与结构的一致性，不能证明象征解释成立。
