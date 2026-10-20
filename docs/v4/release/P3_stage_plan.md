# P3 本机演练与 stage 切换计划

记录：2026-10-21 01:06，北京时间（Asia/Shanghai）。这是 P3 原提示词验收第7项要求的离线计划；本片只写文档，没有运行测试、改 owner 设置、启用模型或访问服务器。

01:41更新：本机管理命令40项目标通过，原旧页面真实HTTP/PG三轮正文已跑通；真实回执DOM缺口已精确复现，不能放行stage。后文初始“尚不存在”状态以本更新为准；真实服务器操作仍为0。

## 1. 当前结论与范围

**No-Go。先完成本机合成演练，再申请 P3 专项 stage 授权。** 默认 owner runtime=v3 和本机组件通过不代表生产可切v4。现有条件授权B/D属于B1固定包`b9a89b6`，不包含P3。本文不改B1包、迁移、服务器unit、Hermes wrapper、CHART_PYTHON或磁盘方案，不提供生产执行授权。

已具备候选：持久Runtime/Journal、core4安全提交、core3/core4读取端、owner首次排队版本选择、线程/无痕/inbox、飞书2500ms合并、双通道Dispatcher、取消/续租及线程HTTP/SSE适配。证据分别在`../evidence/P3/2026-10-21-runtime-api.md`、`2026-10-21-m7-dispatcher.md`、`2026-10-21-M8-scripted-v4.md`及相应ExecPlan。

以下门尚未全过，不能执行stage切换：

| 阻塞 | 放行所需证据 |
| --- | --- |
| 01:00固定头v4为1484通过/42失败，Core581中1项runner工具路径失败 | 原因与定向修复已有独立证据，须02:00新固定tree完整回归及精确PR头CI绿；不能引用旧绿或相加子集 |
| M8原指定47为46/47 | 大脑裁定X03混绑网页/飞书发送契约，保持原四失败可追溯；完成新的获批验收契约，不造Outbox修分 |
| 公开present_options已补齐定向证据，尚缺新固定tree组合验收 | 实际工具→Journal→事件→core4→HTTP回放已有16新PG/139相关目标通过；仍随组合头回归，字段按冻结v1 |
| P1b仍在独立分支，尚未集成本树 | 在v4/integration组合P1b/P3，证明所有物理HTTP入口、可信角色、全停、额度/并发和人工开始门共用中央守卫 |
| 真实K3 encoder未配置 | 本机经审artifact/version/hash接入、计数与1.15+4000上界、拒绝未知计量、actual校准离线证据；供应商实测另授权 |
| 管理命令仅完成本机隔离入口，stage未启用 | 本机40项目标通过；stage目标白名单与受审窗口另实施，不能直接SQL绕门或复用B1授权 |
| 旧页面三轮正文已实测，保存回执DOM失败 | 三轮v3/v4/v3及history正文通过，但旧UI仅读memory_receipts，core4字段为receipts；完整目标1 passed/1 strict xfailed。由前端补兼容后复核，不能隐藏期望失败或给冻结信封偷加字段 |

附件、旧塔罗reading/report等未覆盖复杂输入在v4前置拒绝，不能在stage临时放开。U4仍用Z6接口替身；date_calc披露待脑，P8能力缺口继续诚实降级。真实供应商质量、缓存命中、真实渠道送达不由ScriptedProvider成绩替代。

## 2. 本机预演环境和候选冻结

使用独立可丢弃PG15库/唯一测试schema和完全合成owner，拒绝stage/live DSN；凭据清空、LangSmith/LangChain/OTel追踪关闭。Core/Charts解释器分开，Charts仅做已有引擎本机适配；不启动真实飞书SDK/报告sender，不创建供应商真实端口。

冻结候选代码tree，记录P1b/P3精确SHA、迁移清单/校验和、契约Schema版本、两套解释器/锁及测试数据范围。P1b新增0008与P3组合的应用前后须另验；P3本片没有新迁移。0009留P5b B，不为此次演练占号。B1包始终只含原1–7，不把本演练内容塞回b9。

受信服务工厂须显式构造同repo的AgentRuntime、ScriptedPort和合成meter，再传入ConsultationService的agent_runtime；v3也使用离线模型替身。RuntimeAssembly.require_agent会拒绝缺meter/未审真实meter/不匹配repo/调度容量不足。CORE_RUN_CONCURRENCY及repo容量至少支持当前Dispatcher要求的3；所有worker配置一致。

管理入口已实现并提供本机目标证据（`../evidence/P3/2026-10-21-set-runtime.md`）。下列仅为本机隔离合成owner的默认只读命令，不连接stage：

    python -m mingjing_core.tools.set_runtime --owner <合成owner> --runtime v4 --schema <隔离schema>

实际写入还必须显式`--apply --expect-runtime v3 --request-id <稳定ID>`；反向用v4旧值和新的稳定ID。仅从明确loopback隔离CORE_TEST_DSN读取，校验实际PG15库/角色/schema，拒绝远程、生产和stage；不初始化库或owner。stage支持本片未启用。本文的owner必须来自受信配置，不接受网页传入runtime布尔或模型工具参数。

## 3. 本机 v3 → v4 → v3 操作顺序

下表是待执行的演练，耗时为估计，不是实测。任一步失败保持设置/数据可审，记录安全错误类型后停止该演练，不自动重试或发真实请求。

| 步骤 | 操作与核验 | 继续条件 / 停止条件 | 估计 |
| --- | --- | --- | --- |
| L0 冻结 | 核本机身份/合成owner/空凭据，保存settings.runtime旧值、代码tree和迁移校验摘要 | 非loopback、未知owner/配置、任何真实sender/provider出现即停 | 5分钟 |
| L1 v3基线 | 管理工具只读确认v3；经旧/api/chat发合成文本，等实际成功后读run与旧历史 | run.runtime=v3、core3.0、旧页面正文正确；私密指令不得落入v3长期存储 | 5–10分钟 |
| L2 安装候选 | 只安装显式离线AgentRuntime/Dispatcher，owner仍保持v3；缺meter/容量负例先验 | 默认v3照常；缺v4依赖时请求在写源前拒绝，不能静默降回旧模型 | 5分钟 |
| L3 切v4 | 管理工具核旧值v3、只改合成owner的runtime=v4，保存不含正文/凭据的回执 | owner/旧值不符或有不可解释在途任务即停；其他owner与旧run身份不变 | 2分钟 |
| L4 v4正向 | 新request_id经旧/api/chat或线程消息API排队；lifespan Dispatcher执行，读run/history/events；做一次两工具+提问接续 | 新run.runtime=v4、core4、回执真实、旧DOM显示text→answer；asked/options及seq符合冻结Schema | 10–15分钟 |
| L5 边界 | 同线程串行/跨通道、幂等重放、无痕确认、撤销clean epoch、SSE断线续传、静默HTTP取消 | 来源/权限/撤销/收据任一异常即停；取消≤2秒、partial=interrupted且无最终投递 | 10–20分钟 |
| L6 切回v3 | 停止该owner新提交；等待v4终态或经现有cancel并确认停止，管理工具核旧值v4后改v3，再发新request_id | 新run.core3/v3行为与L1一致；旧v4重放仍core4，同operation不被重标为v3 | 5–10分钟 |
| L7 归档 | 比较三轮runtime/schema、事实/回复/Outbox计数、其他owner不变；仅清演练专属schema | 公开证据只有合成ID/计数/hash，不含正文或DSN；清理目标不明即不删 | 5分钟 |

首次组合估计50–80分钟，不含完整回归、修复和CI等待；不承诺夜间或服务器耗时。本次文档没有执行L0–L7。

## 4. 本机测试闸门与证据

已有真实本机PG目标命令可在指定窗口复跑；以下不是本片新成绩。本机离线目标可先推进，不必等待真实K3 encoder；完整三轮切换仍须管理入口就绪，stage放行必须收口第1节全部门。全量必须北京时间每小时00–15分开始，总测试进程≤4。在冻结源码/隔离PG运行：

    python -m pytest tests/v4/agent/test_runtime_assembly_pg.py tests/v4/agent/test_thread_routes_pg.py tests/v4/agent/test_run_event_replay_pg.py -q
    python -m pytest tests/v4/agent/test_dispatcher_pg.py tests/v4/agent/test_dispatcher_http.py tests/v4/agent/test_dispatcher_handoff_pg.py -q
    python -m pytest tests/v4/agent/test_result_reader_contracts.py tests/v4/agent/test_result_readers_pg.py tests/v4/agent/test_eval_v4_continuous_pg.py -q
    python tools/eval/runner.py --mode scripted --target v4 --output <新的P3本机证据目录>
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q

管理命令和三轮正文DOM组合已实现，见`tests/v4/agent/test_legacy_dom_runtime_pg.py`；完整回执DOM仍strict xfailed，不能宣称整个演练完成。jsdom证明真实DOM和旧JS路径，不提供浏览器布局截图。仅HTTP200或TestClient仍不足。前端独占文件由其负责，主线不回写；本机整合时双方契约以冻结Schema为准。

报告逐项记录开始/结束北京时间、base/source/tree、通过/失败/跳过/耗时、owner切换旧值/新值、三轮run的runtime/schema、幂等operation观察、取消单调时延、来源/撤销及Outbox计数、回执hash和DOM截图路径。实际物理供应商请求必须为0，local HTTP/MockTransport步骤单列。

## 5. 未来 stage 专项计划（本次不执行）

本机演练和精确组合头CI绿、大脑接受P3未完项处理后，另向用户申请明确的P3 stage授权，列出服务器身份、专用库/schema/owner、候选SHA、允许窗口和回滚边界。缺授权或缺任一前置证据，不连接服务器。B1的30/31 Go文件不能代替此授权。

获准后，先只读核stage身份、现有版本、磁盘、迁移和角色权限；备份/新库/部署/停启均须包含在那次授权中。使用stage合成owner和受保护配置，保持owner v3；校验二进制、依赖、两套解释器、Schema、P1b守卫和关闭外发的证明后安装候选。按L1–L7先进行全离线模型验证，不把任何stage文本发供应商。

切**获准stage主owner**到v4前，重新核该owner范围、有效资料授权和在途队列，先关闭新提交并排空/取消确认；使用审定管理工具只改runtime，保留回执。完成v4验证后按原授权恢复v3，比较旧运行身份、历史/core3/core4读取与Outbox状态。stage任何校验/权限/迁移/回填差异或磁盘异常立即停止并保持现状，不自行修了再试。

真实Kimi探针、等价性或T/R/Q/S质量另需用户在线并明确“开始”批次，中央额度与并发规则照常；当前均不执行。真实飞书和报告外发不在本计划内。P3生产切换另写受审操作单并取得那次明确授权，本计划不覆盖。

## 6. 回滚与止损

首选保留兼容代码，仅将获准owner的新operation路由切回v3；冻结新v4入站，保留能读取core3/core4的服务。settings切换只影响新operation，已有queued/running v4依旧按持久runtime处理，不能UPDATE运行身份或直接送旧模型。保留v4 worker至安全drain或取消已确认，防止孤儿任务/错误重发。

部分输出取消后保持interrupted，不能当已验证答复投递；sent/uncertain Outbox保持终态，不重新claim、不删除收据。来源撤销、脱敏、无痕关闭和临时保留策略继续有效，不为恢复旧页面复活正文。任何取消未确认、owner隔离失败、原话/引用/收据不符、未知计量仍发送、危机模板失败都应保持关闭并交审。

不回退迁移、不删v4表/日志/事实/原话，不修改0001–0008既有校验和。若必须回退二进制，先证明旧候选能读取当前schema与core4、冻结所有writer并有已演练恢复方案；不能把B1 b9无条件连到新增P1b/P3状态，也不能套用旧schema4直接连接schema7的回切方式。生产回滚不在本次计划授权内。

## 修订记录

- 2026-10-21 01:06 +08:00：首次建立P3专项离线切换计划，列出当前No-Go、真实候选与未验边界、尚不存在的管理入口、三轮演练/测试门/回滚及P3授权隔离；只写文档，未执行。
