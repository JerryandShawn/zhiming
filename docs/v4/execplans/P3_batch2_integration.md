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
- [x] 项4 main v57点名的评分包v2三项：结构/领域参考/纯judge失败待复核实现，26项定向通过；43号草稿的扩展条款、语义断言迁移、rubric切换和付费校准未自动启用。
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

### 2026-10-27 00:13 评分包v2三项完成（模块未就绪时推进）

本轮业务代码diff仅tools/eval（此外更新本ExecPlan）。judge-packet-v2纳入实际此刻块、合成画像、种子/注入/原生记忆及撤销状态、前轮原话gist/回执/级联关闭、本轮卡片完整字段、实际盘面声明、按类别选至多3条领域规则。画像/此刻/卡片/现有criterion不截断，必要区超预算直接拒绝；记忆12条/80字、盘面10条/80字、保最近3轮gist并始终保留更早effects；总预算不含answer≤6000字。答案全文保持，优先保被引用别名，记录truncation/packet_chars/sha256到私有证据。缺原生此刻时明确missing_evidence，不补造产品块。

F01从真实撤销前的跟进关联和撤销后的删除/撤销账本证明级联关闭，沿已有privacy observer的cancelled（native_status=deleted）等价口径；不由回答文字推断。新报告评分元数据保留实际rubric路径/原字节hash/model/effort（未知为null；LiveJudgeProvider已核high才标high）。没有切换已加载rubric或自行启用未审29题扩展criterion，当前criterion显式legacy_only_pending_brain_review_of_expanded_clauses。

新增brain_review：硬工具/DB/回执/事件或target错误仍失败；仅judge失败且问题类型无已校准revision_enabled证据则待大脑复核，字面疑似且语义高分也只待审。原machine_status/machine_score/failed_assertions保留，未自动放宽0.8通过线。native session和engine均接入；rollup单列needs_brain_review_ids，未决不算通过或失败、不重跑已执行题、门槛accepted=false。needs_human/suggestions可选字段只影响复核，不新增偷偷扣分项。

证据分轮：6574fc32c8a345f695aebc6deb3b6812为16pass/1fail，F01跟进删除后关联字段已清空，原实现无法提取关闭；保留原件，改为撤销前只读保留原关联、撤销后原生验证。80509032a0a3484bad215e3fce9b013e为17/17（13.40s，含旧r39兼容），21286aa6cd6e410ea427b0d543c9c730为7/7（5.35s，补引用别名优先保留），c133fef50b17473e9aa93703d82e495e为7/7（5.21s，补实际rubric元数据）。最后489134020eb9495abe641fcb0919ffbe为26/26（214.44s），覆盖packet、待复核各分支/接受门和原生JudgeJournal持久重放/未知拒绝/隐私。metadata/XML/log根核，Ruff/format120过；不相加称一次全链，没有真实模型或校准请求、未跑全量、未改历史分数/原报告。

23:55（10-26北京）本wake单次SSH仍banner timeout/native255，未入远端。模块首段仍未就绪，P8材料已就绪。下一wake先看模块：就绪则优先记忆合入/候选；否则进入P8项（仅读42第二部分指定段），记住P8不得进入release-mem2，从当前不含P8的提交保留候选基点。所有首发/记忆Go/窗口规则仍有效。

## v57 / 46号优先规则（已全文读取）

首发优先于记忆2.0，记忆2.0优先于其他。首发满4小时只读看一次5xx/异常并记录。记忆stage需47 Go及首发stage成功；生产需48 Go、记忆stage成功、首发已开门至少4小时、无回滚/冒烟正常/日志未明显恶化。窗口2小时、比48写入晚至少20分钟、23:30前结束、避开06:45–07:15；10-27 23:30前走不完停当步等人，自动任务延至28不扩部署窗口。候选不含P8，后续P8只改batch2不动release-mem2。

指定真实题：M01/M03/M05/M08/R02/R07/F01/KU01/KU02/TM01/Q06/A01/TA01、既有安全5题、C01/C05；安全5/5，其余最多错2且M05不得错。沿首发计量/身份/停止/账本/秘密规则，不自动扩大题集或自改判。46号无迁移要求覆盖本计划旧0009安排。

### 2026-10-27 00:21 P8接入开始，尚未完成

main57；模块最新10-27首段仍未记忆2.0就绪（35/37、KU未完），本轮不merge记忆。命理首段已明确材料就绪，按42第二部分2.3–2.6普通merge批准9a8466ec80c1e8ae577c1eea21430e29c4987204，实际merge c9f4bb1f9adf34aea2186428e72040517c79302f，无冲突。private/mem2_pre_p8_base.json保持3b095f397568e783ec05454f855694456bbbca4d，未来记忆候选从此不含P8基点独立构建，不能从当前含P8树直接冻结记忆候选。命理自身3227等证据没有冒称主线验过。

新增metaphysics_intent纯分类基础：仅未引述、非否定用户句子；单值优先合盘/择日/黄历/日运，择日六用途，受信晨报单独标志；不表示第三方同意。目前尚未注册四新工具或接入运行时，下一先做可信资料映射、文档校验/引用来源及P8路由，然后补可见性降级和授权入口。绝不称P8整项完成。

42要求添加新工具前摸清全真状态：原22项可见性测试202922273e5c4db08d224f6502a2e0dc为22/22、0.46s；新增dataclass全部布尔状态为True的实际用例确认原生TOOL_VISIBILITY_CONFLICT。原常驻12+必需6=18；即便降calendar_lookup/set_reminder两项仍16（新synastry必需时17），不能仅删除两个常驻就声称已解决。下一需在不丢必需工具的前提下明确剩余可见性策略；当前保留原产品策略，未绕过15上限或吞异常。

新定向首次0f8762e42b804c33b05b9cfafa185d86为44pass1fail（弯单引号引述未被旧mask_quoted屏蔽）；局部补充弯单引号遮罩后144d257a1c68423aacb414382444ea01为45/45、0.49s。metadata/XML/log已根核，Ruff/check及format120过。只做意图与旧容量基础，不相加称端到端，未跑全量/CI/真实模型。未修改原工具可见性或旧测试契约。

本wake00:15只读SSH true仍banner超时，原生255，未认证、远端命令/修改0。首发e578树/原包不动。继续P8可独立实现项，记忆就绪后优先切回记忆；不重读42全文、不重跑已过TA01/M01/评分包。

### 2026-10-27 00:42 P8受信资料与产物边界子项

新增charts_natal.natal_request：只读已授权服务端snapshot，精确owner/subject/revision/operation绑定；exact映射原生reported，保留秒及微秒，不从时区偏移猜IANA，不默认为clock，缺项/冲突/区间/未知/过去目标/非法坐标返回MISSING_INPUT。纬度两极因后续西占不支持而拒绝。未把新出生字段接入资料确认卡或模型参数，四工具运行时仍未注册，不能把本函数单测称产品闭环。

新增charts_documents：区分time_basis顶层scope和三工具scope（黄历native scope必须None）；核原生工具document_id内容hash、原生time_basis source_sha256与调用方受信worker摘要、严格有限JSON、实际规则met/source及所有登记Pointer。只提升/data路径，不二次提升/charts/i/ziwei_column；重新生成绑定scope/kind/source/payload的文档ID和引用行，不复制上游短别名。hash不是来源认证，调用者必须持有自己adapter实际执行结果，不能把模型/HTTP产物传进来。合盘明确排除持久chart envelope，后续只用授权后临时结果。

persist_documents在原生owner事务/租约/来源版本复核后写现有artifact，无迁移；保存source_versions/source_ids/used_fact_ids/source_refs/run/epoch，重放同operation零重复，已删除不复活。真实PG测试覆盖重放、删除后拒绝、取消/资料变化/来源删除/无痕/危机/篡改引用均不写。当前尚未接agent_chart_lineage/loop_codec、四工具或P8计算路由；time_basis规则登记目前只已核bazi rule_hits，紫微飞化/边界声明需后续明确接入，未宣称完整P8引用展示完成。

最终a1e7d168328a4fdf9d872b7b2be7a51a为44/44、3.07s（原始metadata/XML/log根核），含三份真实donor样例Pointer解析+工具原生内容校验+真实PG版本/撤销+出生映射。先前60c73db330c24770acce48b023528164为8pass8fail：ScopeError继承ValueError被转换、native source实际为对象而非字符串；已在边界保留CoreError并兼容真实具名来源对象修复。2a3be3707bf44b5e9aacd752e02afe65为16/16、e7b802f74e7e4ede9a6381fc3c10a1fd为23/23、2eb8d2c1b296456193836c315d02feb7为20/20均为中间定向，不相加称全链。末次仅格式规整后check/format120通过，不重复刷测试。真实模型/服务器修改均0，无全量/CI。

main57、模块仍35/37未就绪；00:35只读SSH仍banner超时/native255，session34911已结束；PG55480原PID50516只核存活未重启。下一继续P8运行时路由/资料确认/lineage及四工具授权，保留旧容量冲突待裁定，不吞冲突或放宽15；记忆一就绪从3b095f39无P8基点另做候选，首发e578不动。

### 2026-10-27 01:00 chart_skill实际接线子项

已注册chart_skill ToolDefinition并分发到实际应用处理器；schema的system/topic枚举从获准本地catalog读取，运行时严格核体系/章节配对，不给出生资料或consent参数，拒目录穿越/额外字段。沿用原可见性：只有本轮chart_compute成功后才出现，危机不可见，只读且标记可无痕；没有解开无痕读取长期出生资料的禁令，当前无痕原计算仍不可用。

执行时核本步骤名称/fingerprint/原生租约/当前原话，只允许本epoch本seq之前已完成且成功的真实chart_compute。调用原有chart_cache逐项重核原生结果/cache/产物/来源版本，单有ok标志不能读取技能；被撤销产物、变更资料、伪造cache、未完成计算都拒绝。返回本地loader原章和实际版本/hash/字节预算，不产生c/r或保存用户事实，不把技能当专业依据。没有新增模型/网络请求。

第一轮a45ba5bfe6074edd9073ba4f5512fd9f：37/37、3.29s，真实PG成功计算→Journal完成→技能读取；未完成/撤销/资料变化/伪cache/危机/指纹拒绝，原参数和注册表契约同步。新增全部已知topic跨体系无效配对断言后，187381ecba894843a920332c2f33df3d：29/29、3.17s，含旧可见性兼容。两原metadata/XML/log根核，不相加称全链；Ruff/check及format120过。

旧测试修改依据：42 D12明确新增注册chart_skill，注册数20→21及computation_definitions清单补一项；保留默认15工具、原顺序、strict schema、隐私和危机约束，非删断言刷绿。只改对应计数/名单及过时测试命名，未放宽原工具授权。原全真容量冲突仍保留待明确策略，未吞异常/放宽15。

00:55 SSH true仍banner超时/native255（71439已结束），未认证/远端命令/修改0；模块首段仍未记忆2.0就绪。P8整体未完成：下一继续确认资料tz/clock_basis、P8计算路由和lineage、四工具及合盘同意/卡片；不重读42全文或重跑已过子项。记忆候选仍须无P8基点3b095f39，首发e578不动，未跑全量/CI/真实评测。

### 2026-10-27 01:41 P8确认资料时区与记录依据接线

main58仍生效；H1无P8闸门已在独立mem2-gate 41660531发布，模块首段仍35/37未就绪，本轮不提前merge。P8继续仅本batch2树。新增ProfileField的birth.location.tz/birth.clock_basis；确认HTTP入口及MemoryService.save_fact白名单同步，两者共同调用严格IANA/clock-standard-unknown验证。数值UTC偏移不转换为IANA，不把未知依据改成clock。非法值在确认原话/事实写入前拒绝。旧HTTP输入不含两字段仍保持旧路，且不会生成新字段；后续P8准确排盘继续由natal_request缺项闸门拒绝，不能把旧偏移冒充已确认时区。

现有资料确认卡新增IANA输入与时间依据选择，空资料不预选、不从UTC偏移推断；旧候选只展示已有明确字段，勾选授权仍默认关闭。用户明确提交后与原生源消息/授权/版本/幂等一起保存。原无痕/敏感/更正和owner隔离未放宽。Node DOM检查验证新字段初始空、明确选择后带入payload、未知时辰原流程保留；未声称已做不同屏幕视觉截图。

private/safe-narrow-58625d70718d4b998b074c898dd7cd9f为4/4、2.07s，真实PG+HTTP确认新字段、逐字段来源授权、原请求重放、无认证拒绝、另一owner为空、非法/未勾选不写及旧HTTP不猜字段；metadata/XML/log根核。首次1782aff6f30e44069cee2ff9eb4fce43为3pass1fail，测试误用Bearer而原生认证为X-Token，已修测试按原契约调用，不改认证产品。另2c927cc6010d4b5fb93af4e1f5e41289为24/24、1.77s，原profile更正/删除原话后重放不复活及computation参数兼容，原metadata/XML/log根核。两轮均带同一既有Starlette弃用警告，不是失败；不相加称一轮全链。新文件Ruff/check+format120、旧局部改文件AST、node --check、完整原DOM脚本及git diff --check通过。一次命令的PowerShell引号解析错误发生在任何修改/测试执行前，随后用private定点编辑脚本完成DOM测试改动，不算业务测试失败。

01:35单次SSH仍banner超时/native255，session67301结束，远端命令/修改0。真实模型0，未跑全量/CI。P8原生计算路由/lineage/四工具和合盘同意仍未接完，容量策略待精确裁定不吞异常。下一继续实际P8路由或mem2附加段2–5可独立项；模块就绪优先无P8记忆合入，首发e578冻结。不要再重复已过资料字段、chart_skill及TA01/M01/评分包测试。

### 2026-10-27 01:58 显式P8应用计算服务与实际子进程

新增ChartsService.evaluate_time_basis及独立p8_chart_service，仅从已授权原生snapshot构造请求，调用实际P8ChartAdapter隔离Charts进程；调用前取真实worker来源hash，返回后核owner/subject/revision/operation及原生文档。明确返回physical_instant_confirmation_required、边界声明和不支持能力，不自动修正出生资料，不写事实或artifact。传输异常只给固定安全错误，不泄漏stderr；原CoreError保留原义。默认旧ChartsService.evaluate/factory未切换，尚未接Agent chart_compute/cache/alias链，不把服务子项冒称产品闭环。

private/safe-narrow-94bb0462142f45019ea1027f6c4014ef：3/3、6.71s，原metadata/XML/log根核exit0、fail/error0。实际PG确认资料→prepare_chart→真实Charts子进程→原生有归属盘面与references，snapshot/owner revision不变、model_calls/writes为0、artifact为空；另验证缺IANA/跨owner在factory前拒绝及私有stderr不外露。Ruff/check及format120通过。无完整测试/CI/真实模型/服务器修改。

main58/模块首段35/37仍未就绪，本轮不提前merge；H1独立41660531和无P8路线保持。01:55本wake只读SSH仍banner timeout/native255，session2306已结束，未认证、远端命令0。下一接Agent实际P8路由/cache/lineage及四工具授权，紫微引用/合盘同意和容量策略仍待；不重复已绿子项。

### 2026-10-27 02:17 P8临界提示引用绑定

在现有verify_p8_document/reference_rows纳入原生boundary_alerts，作为实际命中规则引用，保留原文档Pointer/测量值/候选，不信上游短别名。必须met/critical为真、default_formula_changed为假、原规则版本/候选存在，instant_id/source_instant_id/UTC/原柱一致，并唯一绑定真实true_solar主盘。每条依据只许本次time_basis.items/source_variants中该候选的原生字段，不借用另一个已存在候选或interpretation对象；真实Pointer和值hash保留。未推断新临界值或改动出生事实/默认公式。紫微飞化引用及Agent alias持久链仍待，不冒称已接完。

private/safe-narrow-e09e3c22642b4463a47e6d1aee484735为29/29、0.85s，metadata/XML/log根核exit0/fail0/error0；含三份原生样例引用、实际临界规则及12个精确拒绝变体（假命中、非critical、改公式、版本空、时刻/UTC/柱不符、重复主盘、无候选、借另一候选、文档外引用、缺失路径）。未修改原样例或旧gold。

同时修正应用服务对subprocess.TimeoutExpired的安全转换，超时命令/stderr不外露；private/safe-narrow-5b56223757384f3d843e4e916811e3c8为4/4、3.42s，原metadata/XML/log根核，含实际PG→Charts worker通过新增临界校验以及普通/超时错误负例。分轮不合称一次全链。Ruff/check/format120/git diff--check过，无全量/CI/真实模型/远端修改。

main58未变，模块仍35/37未就绪，不提前merge。02:15单次SSH仍banner timeout/native255（session51663结束），未认证/远端命令0。原PG55480 PID50516仅核存活，未启停PG。H1无P8闸门41660531保持已发布，记忆路线仍mem2-gate。下一继续P8真实Agent路由/cache/lineage/紫微引用/四工具与合盘授权，或模块就绪优先无P8记忆合入；不重复已绿子项。
### 2026-10-27 02:37 紫微飞化真实盘面引用

新增p8_ziwei_references并接入verify_p8_document/reference_rows：对每个原生ziwei_column，以其实际星曜/宫位和声明的获准具名table_id重算原生palace_flying_transformations，使用原生rebase_column_evidence规整到当前文档后逐内容hash一致核验；包含实际表来源摘要/版本/学校/星曜定位/缺失或歧义状态/原生运限可用性。不修改上游计算或资料，不把未出现运限补成已计算。

飞化全部*_pointer/evidence_paths必须位于该盘本身的ziwei_column且实际可解析；不能跨另一个候选或二次提升。登记原生column和flying对象为chart事实引用，附真实Pointer/value_sha256，不制造met或rule引用，不借用短别名。解释规则引用仍只来自真正命中rule_hits/临界规则，后续仍需Agent原生持久化及alias链，不把本子项冒称Agent闭环或四工具完成。

private/safe-narrow-cd7798da1191445fa00ebcb5410d83bb为38/38、1.17s，metadata/XML/log根核exit0/fail0/error0，含原生三份样例、飞化正例/八种篡改拒绝及原文档临界规则。private/safe-narrow-823724006c01486b8fba34647f719883为4/4、3.28s：实际PG确认资料→真实Charts worker→新增飞化文档校验及错误负例；原件根核，不把两轮合称一次全链。因本次更改产物验收入口才复核真实worker，不重跑无关TA01/M01/评分包。Ruff/check/format120/git diff--check过，无全量/CI/真实模型。

main58/模块首段35/37未就绪，不提前merge；02:35只读SSH仍banner timeout/native255，session47201结束，未认证/远端命令0。原PG55480 PID50516仅确认存活，未启停。H1独立无P8闸门41660531保持发布；首发e578/r46冻结。下一优先实际Agent P8路由/cache/lineage、四工具/合盘，容量策略仍待裁定不吞异常或放宽15；模块就绪立即优先无P8记忆路线，不再重复已绿飞化/临界子项。
### 2026-10-27 02:58 P8原生文档与Pointer引用持久记录

新增p8_reference_records：在既有原生authority/资料版本/隐私租约事务内先保存完整document，再按(document_id, Pointer, kind, value hash)派生独立artifact或interpretive_claim引用记录，绑定原文档实际ID/revision及run/epoch/事实/原话版本。幂等ID/operation均从本受信步骤和引用派生，删除后不复活。仅内部受信计算调用方可用，不是模型或HTTP输入入口。

单个bundle确定选择至多10条引用，临界规则优先，选择规则时连同全部真实chart依据；超出容量不割断证据闭包。完整产物仍按document保存，不信上游短别名。该上限目前是bundle保存/复核层；Agent跨工具本轮总注入上限和已完成Journal绑定仍须下一步接线，不能称已经注入c/r。

verify_reference_bundle只读重核实际文档和每条引用的内容、owner/subject/run/epoch/修订/撤销状态、原文档Pointer清单、完整无重复投影；返回原资料+doc+引用的真实版本闭包和后续主线可使用的原生记录证明。没有跳过原生已完成步骤证明或把本helper单独当完整chart_lineage。下一接Agent chart_compute/cache/lineage及真实completed步骤和alias输出，默认旧路径仍未切换；四工具/合盘未完成。

private/safe-narrow-90278c670320415a84de0f5aee37cdfa为12/12、4.42s，metadata/XML/log根核exit0/fail0/error0：真实PG幂等无重复、chart/rule各自ID和doc版本闭包、10条选择保规则全部依据，删除/更改doc或引用、资料变化、取消、重复/缺失记录和错误修订拒绝。首轮d81610b76ec54c73b5753aa0fa85db9b为11pass/1fail：Python True==1让清单比较误接受布尔修订；已增加全部投影严格整数及类型敏感fingerprint比较，原失败保留。没有放宽该负例或原分。Ruff/check/format120/git diff--check通过，无全量/CI/真实模型。

02:55只读SSH仍banner timeout/native255，session74476结束，未认证/远端命令0。main58/模块35/37仍未就绪，不提前merge；PG55480/PID50516仅核存活未启停。H1无P8路线41660531及首发e578冻结不动；模块就绪立即优先mem2-gate合入和41/46门。续项不重复已绿边界/飞化/TA01/M01/评分包测试。
### 2026-10-27 03:25 实际Agent P8计算、缓存及c/r接线

按42 D1/D3/D4/D5/D6，execute_chart准确时刻八字/紫微默认进入真实evaluate_time_basis；明确approximate/interval/unknown或time_unknown保留原calculate并标明“旧口径，未做真太阳时与交界提示”。西占保持原calculate。准确资料缺IANA/clock_basis不得静默降旧路，返回MISSING_INPUT；缺资料的确认卡完整交互仍待后续，不把错误码当卡片已完成。

新增agent_p8_charts：原生authority/隐私二次闸门/prepare snapshot→在PG事务外实际Charts子进程→真实文档校验→新短事务复核租约及资料→原生doc/Pointer记录和缓存。cached_chart识别P8并重核完整doc/引用/来源版本，chart_cache和chart_lineage仍要求当前epoch唯一真实已完成chart_compute步骤及完整输出一致，再向原有loop_codec.verified_versions/extend_aliases提供c/r证明。未完成、伪工具输出、撤销doc或引用、资料变化、计算后取消均拒绝；重放原步骤不重算。chart_skill复用相同原生cache证明，已实际验bazi/ziwei两种。

根据实际requested_system筛选本次引用：紫微不借八字rule_hits，八字不塞紫微整列；原生临界提示保留。单bundle存system/limit并在复核中严格核一致；额度来自同run/epoch已完成原生工具输出的实际专业记录ID并集，后续计算只用剩余槽，不听模型传限额。同轮两次实际计算已验c/r总数不超过10，规则保全部依据，额度耗尽可保完整doc但不新造引用。四个新工具尚未注册，计数器预留其原生名称不代表它们已完成。

loop_codec的P8工具消息只投影真实reference_views、可见主/比较盘摘要、口径方法、全部临界提示及physical_instant_confirmation_required/能力限制；完整原生doc、持久记录和重复calculation留私有Journal/cache，不整包注入模型。原生完成后才加入已验证别名。脚本Agent已通过实际tool_message→c/r→最终core4.0发布及used_claim_ids绑定，不是只测纯helper。脚本模型0真实请求，排盘库本机真实运行。

测试契约变更：旧PG测试与backfill_support原本保护旧引擎重放/隐私/回填/已完成证明，按42 D3把其fixture明确改为approximate±1分钟，使这些断言继续验证被批准保留的旧采样路径；未改产品去识别测试、不设隐藏开关。原profile函数默认exact仍保留，新增P8用例走原生确认exact+IANA/clock_basis。旧“只调用1次引擎”断言改成实际三个采样点各1次，重放不新增和隐私无写仍严格保留。新P8测试补准确缺IANA拒旧路、真实两体系和最终发布，因此没有拿不确定资料替代准确入口验收。

证据分轮（metadata/XML/log全部根核，不相加称一次全链）：
- 4d84a682b06a40929b786dd0cfb43975：45pass/3fail；新紫微测试误用不存在basics主题、两个旧准确fixture改采样后仍期待只一次；按真实catalog和三采样契约修测试，原件保留。
- 53de47a3a4f34af4ad582dc97f3dbf2e：48/48、38.47s，实际P8+旧计算/技能/隐私/lineage。
- 13e30f8a3b594910bdade3c21667f949：10/10、22.08s，新增P8工具消息投影与脚本Agent最终发布。
- 61d8cb2a4f8e440e94d9fa8e07be66a3：22pass/1fail；同轮第二次测试用了未complete的Harness.call，原生已完成证明正确拒绝。补真实Journal.complete后不改产品闸门。
- 最终30f24c179df345b79d2213462d1920e1：51/51、53.81s，含实际P8/同轮两算≤10/原生引用和旧回填隐私、原分、Outbox终态兼容。Ruff/check与format120共11文件及diff--check过。

本轮无完整tests/v4/CI/真实模型/服务器修改。03:15一次SSH仍banner timeout/native255，session29141结束，未认证/远端命令0；PG55480/PID50516只核存活未启停。main仍58/模块35/37未就绪，H1独立无P8 41660531保持发布，首发e578/r46冻结。下一P8四工具/合盘同意卡/缺资料确认卡、可见性容量裁定及system临界文案/档案摘要等剩余项；不要再重做已过实际计算lineage或纯helper。模块就绪优先无P8记忆合入与41/46门。
### 2026-10-27 03:43 三个P8日期工具实际接线

注册daily_transit/window_search/almanac（独立p8_definitions/p8_parameters）。只接受1901–2099年绝对日期、六种原生择日目的、最多366日区间和原生分页<=31；拒出生值/owner/consent及额外字段，不把相对日期冒充已解析日期。定义说明快照12:00/排序限制/公共黄历与本轮派生记录效果，不声称事实已保存。DailyTransit合法复用日期参数基类，不含桩处理器。

将原metaphysics_intent纯分类真正接到原生source的VisibilityState，三工具只对应daily/window/almanac各一项必要工具；引述/否定/无关不开放，synastry意图不误开其他三个。无痕/危机隐藏。原15上限/常驻顺序/全真旧冲突保持，不吞ToolVisibilityConflict。注册数21→24是42新增三工具的字面契约同步，旧15条实际披露上限断言保留。复杂必要组合仍有已知容量缺口待裁定，不借正常场景通过宣称全容量问题已解决。

agent_p8_tools执行原生步骤指纹/租约/隐私，短事务准备→事务外真实P8ChartAdapter隔离计算→短事务复核→verify_p8_document/原生doc/Pointer保存/已有cache；daily/window从已授权snapshot读取准确出生值，almanac仅当前source空facts快照，不读出生档案。原生worker返回实际三体系快照、单日择日样例和黄历，scope/hash/真实规则Pointer全核，不写用户事实。工具本身不产生真实模型请求，窗口大范围可能触发45秒原生计算时限，不延长/不虚造部分成功。

新增agent_p8_tool_lineage，只接受同run/epoch/name唯一已完成Journal完整输出与受保护缓存，复用原生版本闭包/引用撤销/10条剩余槽；loop_codec._registries新增三工具分支。P8 tool_message按通用工具投影原生tool_data、限界和选定引用，不注入私有documents/persisted。真实脚本Agent黄历→工具消息→最终core4.0已过，事实仍空。

证据（原metadata/XML/log全部根核，分轮不相加）：
- 0b34ea304ad84e59b8df33e723bd1106：57pass/3fail；测试把原话/事实等全部alias数也算进c/r<=10，实际工具已成功且已完成证明通过；修断言仅数专业c/r并保留repo.verify_versions检查，未改产品限额或来源闭包，原件保留。
- 970bc97bcefd46ea9c2ff80029163c3d：60/60、10.89s，三真实工具/缺出生黄历且禁止fact读取/未完成与伪输出拒绝/缓存重放/引述否定无关及无痕危机拒绝/schema拒绝/旧可见性与15上限。
- 最终cbc128b42f984fdf9434c932afac03e7：24/24、8.50s，新增实际脚本Agent黄历投影与最终发布、旧context可见性兼容；两个成功轮不冒称完整全链。Ruff/check+format120共12文件、diff--check过。

main58/模块首段35/37仍未就绪，不提前merge。03:35 SSH仍banner timeout/native255，session72089结束，未认证/远端命令/修改0。PG55480/PID50516仅核存活未启停，无后台测试/模型/新CI，无完整tests/v4。

尚未完成：synastry原生同意卡/24小时单次授权与临时结果；准确缺IANA/clock_basis返回MISSING_INPUT但完整补资料确认卡仍待；容量精确裁定、临界文案/命理档案摘要及晨报daily可信开关接线。P8整项未就绪，不能提前全量/冻结/部署/真实评测。下一继续这些剩余项，不重做准确排盘主链/三日期工具或旧绿轮；模块一就绪优先独立无P8 mem2-gate合入与41/46门。H1 41660531和首发e578/r46保持冻结。

### 2026-10-27 04:03 合盘原生单次授权与网页确认接口

按42第2.5节新增原生synastry_consent实体种类，沿既有core_entities保存，没有新增SQL迁移。应用服务只接受同owner已授权的两个不同subject、原生准确且明确确认的出生资料；所有资料来源和原话区间通过既有投影/撤销核验。绑定双方subject资料修订及精确fact/message版本，不用全owner修订号（否则创建/确认授权本身会使授权失效）。请求卡片只显示人物称呼、用途、确认文案和状态，不输出任何一方出生值。

原生授权先pending_confirmation，聊天“他同意了”不能改成granted。新增认证网页POST请求/GET确认卡/POST明确confirmed布尔确认接口，沿原X-Token认证；模型consent、出生字段、字符串true、布尔修订号和其他额外输入拒绝，错误不回显提交值。跨owner/未授权人物404，不提供HTTP consume接口。真正网页按钮展示及Agent第四工具尚未接入，不能把后端接口称完整确认卡交互已完成。

确认回执绑定真实请求operation_id，Clock记录granted_at与24小时expires_at、uses_left=1。内部consume只能在owner事务中按原人物顺序/用途/未过期/资料及来源未变消费一次；并发两次消费只有一次成功，重放确认不能延期或重置已消费授权。未来工具调用方仍必须核原生租约/已完成步骤并先走缓存重放，本服务不伪造ToolContext。合盘结果尚未计算/持久化，不建chart/fact/note；将新授权kind纳入现有privacy_foundation闭包，撤销任一方出生来源或请求来源会删除授权且不能复活。

证据（原metadata/XML/log均根核，分轮不拼全链）：
- private/safe-narrow-d516cdde96f34aba935481af649a802e：16/16、6.72s；原生PG授权/单次并发/用途和人物/24h精确边界/两方修订/来源撤销、HTTP认证和严格schema。
- 最终private/safe-narrow-d1389d950242445791a651d8da089f79：22/22、10.87s；新增重放不续期/普通消息不自失效/请求后资料改变拒绝确认，加原资料确认HTTP兼容。1条既有Starlette/anyio弃用警告，无fail/error。Ruff/check、format120、两个旧文件局部AST、diff--check过。没有完整tests/v4/CI/真实模型/远端操作。

模块状态已变化：其日报公开H1已普通合并，候选9ef726257034a391c94191fa60789baa4afbd223的KU01/KU02及指定37/37、新变体4/4通过，但完整tests/v4为4795pass/11fail/193errors/72skip，exit1，仍明确尚未记忆2.0就绪。没有替模块修代码/重跑/提前合并或冒称主线验过。03:55本轮SSH仍banner timeout/native255，session90084完成，未认证/远端命令/修改0。原PG55480/PID50516仅单次核存活，未启停，无后台测试。

剩余/下一：继续synastry实际网页确认按钮、原生Agent第四工具和不进档案/反思的临时结果；然后缺资料确认卡、可见性容量精确裁定、临界文案/档案摘要及晨报开关。P8整体未就绪，不提前全量/冻结/部署/真实评测。模块一就绪优先无P8 mem2-gate合入与41/46门；首发e578及H1 41660531保持冻结。
