# 第二批双轨续作（main v57，沿用v56省额度）

## 授权与边界

2026-10-26 人类直接要求恢复 v56/v55 双轨，到北京时间 10-28 22:00。中档、无子代理、测试进程至多2。首发 e578e2d 工作树冻结；本树从该提交建立，分支 v4/batch2-integration。P8仍不部署、不发真实模型请求；记忆2.0仅46号指定真实评测，以及47/48 Go放行的stage/生产，旧全部禁止条款被v57覆盖。

## 当前断点

- [x] 读取 main v56 顶部及 v55 双轨；恢复20分钟自动任务。
- [x] 一次只读 SSH 探测：banner 超时，未进入远端命令；本机命令包装退出1。没有远端修改。
- [x] 独立工作树建立；读取42号第一部分1.4及涉及路径。
- [x] 项1 TA01本机脚本修复：P1–P7/E1–E4完成；TA01两轮（pick/auto，显式/省略ID）、TA02/03/04/AX01及三条真实HTTP路径定向通过。没有真实模型评测；最终记忆候选全量/CI/真实门仍待后续。
- [x] 项2 M01：只读38号第八节/v40精确修法后实现晚间默认值已过去则保留未来原时间；37项兼容定向通过，9项加强脚本断言通过，见下方分轮证据。
- [ ] 项3 记忆2.0候选：模块线首段真正就绪才普通merge；41号附加段接线，R31不发任何迁移，撤销用变更ID+修订号，migrations与e578逐文件相同。03:00归档/反思仅脚本。46号脚本门、完整tests/v4、CI后冻结v4/release-mem2并写候选就绪+SHA；两份mem2执行单；仅46号指定约20题真实评测一页回执。
- [ ] 项4 评分包v2：开始时只读43号第六节，仅tools/eval；脚本验收。
- [ ] 项5 P8：命理线首段真正就绪才接入；开始时只读42号第二部分2.3–2.6；完成后一次全量及第二批脚本门。

## 已观察实现

TA01当前TarotRead强制draw_id；execute_tarot要求显式字段等于run.request.draw_id。runtime_assembly拒绝draw_id，线程SendMessage无该字段，面板readings对v4直接拒绝。当前评测先ThreadService.receive再ThreadIngress.queue，需改用共用受信揭牌入口，保留原话来源/幂等/归属，不猜最近牌阵。尚未修改产品或跑测试。

### 2026-10-26 22:59 实际增量（覆盖上句尚未修改状态）

42号P1–P3已实现：TarotRead.draw_id可省略，执行时只取权威run.request.draw_id；显式其他ID仍ScopeError，输入指纹继续按实际参数核验，不补造工具参数。描述同步。新增真实PG验证省略/显式读取、重放不改牌，以及“已有揭牌但run未绑定时拒绝猜最近牌阵”。本次仅工具层增量，P4上下文及P5–P7产品入口/E1–E4评测尚未完成，不宣称TA01端到端通过。

原首轮private/safe-narrow-c63b875ba90d4b6ebe7827b374381a74为14项fixture连接错误（本机55480 PG未运行），exit1原件保留。未改测试绕过，未停其他PG；恢复原private/pg-p0的PG15实例，前台session13558，自动恢复后22:57:58 ready。第二轮private/safe-narrow-13a884050dff48d7ad0022ef819c432e exit0、14/14、6.63s，metadata/XML/log根读，0fail/err/skip。Core环境无ruff模块的首次命令失败保留；使用既有.venv-core/Scripts/ruff.exe，check和format120均通过，不装依赖。真实模型/远端修改/外发0。

本次22:55只读SSH探测仍banner超时，已捕获原生exit255，未认证/进入远端命令；下次探测至少20分钟间隔。模块首段尚未记忆2.0就绪、命理最新10-26首段尚未达到P8接线材料就绪，不提前合并。

## 省额度与交接

每wake单次SSH探测，检查两线日报第一段；不通且无可做项时仅一行日报结束。大文件只读当前项；每项定向测试，连续同错两次记录后换项。每项实际完成后提交推送；40分钟实质推送。首发SSH恢复立即优先37号stage，成功回执后等31号Go窗口。连接阶段R30，远端命令失败按执行单停；不改网络/SSH/认证。

## 未验证

TA01及第二批各项尚未实现/验收；模块线首段“尚未记忆2.0就绪”，命理线现有日报未见P8接线就绪。首发stage/生产均未完成。

### 2026-10-26 23:23 实际推进（覆盖上句TA01状态）

共用TarotRevealIngress在接收原话前核owner、subject、已揭示状态、原生事项授权及非无痕线程；所有路径只显式绑定用户提交的draw，不猜最新牌阵。runtime_assembly只放开draw_id，仍拒绝附件/reading/selection/parent；面板readings、旧chat及线程messages接入相同服务。现有模型服务仍执行原生run/ToolBatch/Journal，来源和幂等不另造。P4系统事实从权威租约run取draw id/问题/牌阵，不含牌面，牌面仍须tarot_read读取；P8飞书按钮不做。

评测揭牌动作走同一产品入口，记录每轮可见工具及真实调用工具（仅名字）；TA01脚本可省略ID，原expect/gold不变。TA04放新scenarios_v4_batch2目录，schema仅扩TA04，避免污染固定首发48题集合；AX01从真实scenarios_v4_core30读取。

证据分轮，不能相加冒充一次完整全链：
- private/safe-narrow-dcb7ebb744ea487f8dcee5bf510ee397：23pass/7fail。6项因新校验误把原生case.status=open当active，改为复用原生selected_cases；1项旧测试仍要求所有draw输入“不支持”，按42改为共享授权路径并保留附件等拒绝，失败原件保留。
- private/safe-narrow-318bad7a44124c99872bd7b4e550b2d4：29/29，13.31s，含TA01两轮4模式、入口幂等/owner/事项/未揭牌/删除/无痕拒绝、runtime及线程兼容。metadata/XML/log根读0fail/err/skip。
- 增补三条真实HTTP执行及5个场景：首轮373d78b0cdc14beda3435902b388509e为13pass/2fixturefail（TA04未加入schema、AX01文件路径误指），原件保留；修后f1a648c2e4e34d1196fb81417784ccb2为15/15，10.12s，metadata/XML/log根读0fail/err/skip。三条HTTP均实际执行tarot_read并在随后模型请求读取真实工具结果。
- Ruff/check及format120过；旧web单体只做新增小段，AST语法过，未整文件格式化。未跑完整tests/v4或真实评测，按v56等记忆候选阶段。

本wake23:15只读SSH仍banner超时/native255，无认证/远端命令；模块首段尚未就绪（35/37原脚本、KU未完），命理尚未接线就绪。下一项M01，开始时仅读38号第八节和对应followup代码。原隔离PG session13558仍存活，不停其他PG。

### 2026-10-26 23:40 M01完成与新发现

按38第八节及main v40第5条：规整后的跟进时间不晚于now时保留模型原due，原due也过去才拒绝，当前时间只取一次；原18–22:59明确时刻、23点后顺延和set_reminder规则不改。

首轮606ade0795c945b599798d7d7fe26c88为12pass/4fail，未改gold：真实路径还在规整前被schedule_metadata以event_day!=due_day标date_conflict，单做v40回退无法修复。最小补正仅schedule_followup且日期精度的事件允许跨日候选due进入原有规整/未来校验；set_reminder及有明确时刻的事件仍沿原date_conflict。事件event_at仍来自原话解析，未改成跟进日。

修后e9820d59dda04178bd3eece18029a9d5：37/37、24.91s，覆盖旧v39早/晚/静默时间、今日过去时间规整、真实写入/幂等/无外发、提醒显式授权及新晚间边界。再加强回归变体的硬DB期望（仅内存克隆，不改M01 YAML），4f0efa0c0fba4a319dd3f9163af85d15：9/9、9.54s，正例4个完整脚本passed、两种原due也过去的负例不写跟进、3项仅date-only-followup放宽政策断言。metadata/XML/log根读；分轮不相加称一次全链；真实模型0、服务器修改0。

23:35单次SSH仍banner超时/native255，未进远端。模块尚未记忆2.0就绪，不能merge；命理首段现已“P8 接线材料就绪”（9a8466ec），仅登记前置，不提前合并。下一优先重看模块第一段，就绪则做项3；若仍未就绪，记录等待并转项4评分包v2（只读43第六节），不停止工作、不重测TA01/M01。

## v57 / 46号优先规则（已全文读取）

首发优先于记忆2.0，记忆2.0优先于其他。首发满4小时只读看一次5xx/异常并记录。记忆stage需47 Go及首发stage成功；生产需48 Go、记忆stage成功、首发已开门至少4小时、无回滚/冒烟正常/日志未明显恶化。窗口2小时、比48写入晚至少20分钟、23:30前结束、避开06:45–07:15；10-27 23:30前走不完停当步等人，自动任务延至28不扩部署窗口。候选不含P8，后续P8只改batch2不动release-mem2。

指定真实题：M01/M03/M05/M08/R02/R07/F01/KU01/KU02/TM01/Q06/A01/TA01、既有安全5题、C01/C05；安全5/5，其余最多错2且M05不得错。沿首发计量/身份/停止/账本/秘密规则，不自动扩大题集或自改判。46号无迁移要求覆盖本计划旧0009安排。
