# P3 可信循环配置切片回执

- 时间：2026-10-21 01:50 +08:00（北京时间）。
- 分支/验证基底：`v4/p3-agent-runtime@5218c4ea61dd018272ab989de0c6816117dc6e6d`上的本片工作树增量；由root统一提交推送，PR保持草稿。
- ExecPlan：`docs/v4/execplans/P3_runtime_config_2026-10-21.md`。
- 真实供应商、服务器、飞书、主干合并均0；无新依赖或迁移。

## 完成了什么

固定读取仓库`config/runtime.yaml`，没有路径参数、环境替换或HTTP/model配置入口。严格版本1、未知字段、重复YAML键、精确整数（布尔/浮点/字符串不作整数）、正值和批准硬上限校验。读取失败/损坏阻止构造AgentRuntime；默认v3仅导入类型，不读取文件，仍可构造。可信构造可显式注入RuntimeConfig，重新校验后使用，普通dict不能冒充。

配置各键实际对应LoopPolicy/RunControl：interactive最大40迭代/480秒/每步6工具，background60/1200/10，重复3，lease150秒、renew20秒。可以调低，不能抬高；renew须小于lease。生产以PG持久lane选上限，request.depth保持原值但不能扩大interactive。组件直接构造不带lane的LoopPolicy仍保留既有standard/deep语义，旧夹具没有修改。

每run当前epoch在真实owner事务和`_leased`行锁下保存`usage.agent_runtime.limit_epochs`。pin包含规范配置、config SHA、owner/run/subject/thread/lane/epoch/depth、截止时刻、来源标记和自身校验摘要；不含原话、推理或密钥。每次恢复核PG身份、scope/线程、取消、当前lease/epoch及原pin；并发只能保留首份配置，后到可信构造不能覆盖。新epoch保留旧pin并沿用该run原配置。旧候选已有Journal但没有pin时只首次补并标`legacy_unpinned_journal`；已成功旧run无pin仍按原信封重放，不申请新lease或新pin。

持久deadline不因重启/重生延后；初始lease收紧到配置值，之后按renew间隔续到配置lease。时间仍由注入Clock与原单调钟控制，测试TZ=Asia/Tokyo，未改产品时区或宿主设置。hash用于完整性校验，不是独立授权；租约/owner和PG状态仍是权威。

## 评测分数与实际验证

这是本机PG15目标验证，不是P3原47脚本、真实质量、完整回归或CI成绩。本片单个pytest进程；使用既有P2 Core解释器，PG回环55480的专属可丢弃schema，fixture清供应商凭据/关闭追踪并拒绝外部HTTP与子进程。实际取消测试只放行127.0.0.1合成HTTP服务。

首轮新配置/PG/原Loop控制83 passed/10.29s。扩展轮152 passed/1 failed/39.08s，失败是新测试把旧租约错误写成EvidenceError，实际repo正确抛LeaseConflict；只修该新case的精确类型，无旧测试改写和生产闸门放宽。

最终命令：

    python -m pytest tests/v4/agent/test_runtime_config.py tests/v4/agent/test_runtime_limits_pg.py tests/v4/agent/test_loop_cycle_controls.py tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py tests/v4/agent/test_private_runtime_pg.py tests/v4/agent/test_dispatcher_handoff_pg.py tests/v4/agent/test_merged_regeneration_pg.py tests/v4/agent/test_crisis_unmetered_pg.py tests/v4/agent/test_crisis_turn_sources_pg.py tests/v4/agent/test_runtime_assembly_pg.py tests/v4/agent/test_thread_routes_pg.py tests/v4/agent/test_present_options_runtime_pg.py -q --tb=short

**171 passed/53.80s、0skip**。唯一warning为既有Starlette/AnyIO弃用别名。覆盖低iteration/每步工具/重复限制真实减少执行；真实PG deadline与低lease/renew；深度/通道分离；SystemExit后过期重领不换配置、不延deadline；下一epoch沿用旧配置、双worker一份pin；坏/超限/自洽重算hash仍不能超批准限；身份/旧epoch/布尔epoch/旧lease/取消拒绝零模型；无pin旧成功run兼容；原Runtime/无痕/U41/撤销重生/租约移交/options/HTTP入口保持。

另一次真实静默loopback HTTP取消与实际PG续租：

    python -m pytest tests/v4/agent/test_dispatcher_http.py -q --tb=short

**2 passed/1.82s、0skip、0warning**。本片不重新报告或择优改写原M7/M8已记录的各次取消时延。

六个本片Python通过Ruff E/F/I/B/UP/SIM、format120及AST400/60检查；最大文件308行，无函数超过60行。原有已跟踪两文件diff check通过，其余新增文件同样无行尾空格。

## 关键文件与身份

- `config/runtime.yaml`、`agent/runtime_config.py`：只含实际生效的循环/租约安全键，加载与可信类型。
- `application/runtime_limits.py`：受租约保护的epoch pin、原配置恢复、deadline/lease收紧。
- `agent/loop_policy.py`、`application/agent_runtime.py`：最小lane约束/配置接入，未改loop_cycle/codec/toolkit。
- 新测试`test_runtime_config.py`、`test_runtime_limits_pg.py`、本计划和证据。

默认规范配置SHA256：`6e3402d6ef59ea9e3b57bbc17b73a9b7cdc409df873869aa0d6252bfa0eefe65`；当前runtime.yaml工作树字节SHA256：`f1d3fa666e2afb57f3fc090f90a1a6a6e27df0dd768a2fd9cfaded38a4974c3d`。规范摘要不依赖YAML换行/键顺序，Git提交字节身份由root发布时另映射。

| 工作树源文件 | SHA256 |
| --- | --- |
| agent/runtime_config.py | e11a1448d043a60bf621d43986e409b3f1b148b705768e7705e31d51730081fd |
| application/runtime_limits.py | f11d17d98da74f52780c7d7c248b97248bb07f5ba1e3d8ad898d975fc55fcae5 |
| agent/loop_policy.py | 43a602f3014d2ed86ce4c1718187f1abc20c8a4b4e49dc6a840b3cb38f4d2a0c |
| application/agent_runtime.py | 17001e25f9ea6ac9383b98d99c1f2e790417939af8de980e32152b285075cd82 |
| tests/v4/agent/test_runtime_config.py | d2127665b96048383e444aec9e92fdea6f7ad40b8bf566c9211c5b3a23a12d51 |
| tests/v4/agent/test_runtime_limits_pg.py | bd52ba74024229be63c6e49e0bdeab4349f7e30dd563bd58f1c5b91afdfb4649 |

## 数据库、偏离与回滚

无迁移，仅当前run原有usage/deadline/lease字段；配置metadata无业务正文。蓝图§3.2明确按通道，覆盖了旧Runtime按用户depth扩大循环控制的差异；不改变原request、上下文深度或提示词策略。没有新HTTP/API参数。回退不要删pin或历史状态；保留兼容读取，已有run仍须在原pin限制下恢复，不以重启重置时限。

## 未验证/已知风险/后续

尚无本片完整固定头Core/v4回归、精确头CI或服务器证明；当前P3未完成整阶段验收。只读工具并行未在本片实现。P1b中央额度门、实际K3 encoder、真实模型质量和报告后台接线均另轨；这些安全配置不能替代它们，也不能授权自动真实批次。旧DOM完整正文演练和回执显示由root独立推进，先前97cd审计快照保持原状；最新发现需引用root的新DOM证据，不在本片改前端或公开信封加别名。

本片无新增产品待决，代码冻结交root统一提交推送。
