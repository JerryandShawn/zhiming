# P8 第二批接线说明 · 42号裁定

本线入口可供主线接入；本文不声称已经注册Agent工具。只读合成测试，真实模型请求0。
依赖既有requirements-core.lock与requirements-charts.lock，CHART_PYTHON指向隔离Charts解释器。
Core调用P8ChartAdapter(owner_user_id, python=CHART_PYTHON, timeout=45)，不要在事件循环同步阻塞。
主线在线程中执行并传递取消/截止时间，不能用取消外层任务冒充子进程已经停止。

## D1–D12落地责任

| 裁定 | 本线实际入口与契约 | 主线动作 |
| --- | --- | --- |
| D1 | time_basis(request)准确八字/紫微；calculate(...)西占或旧结构 | 按体系分路，保留各自actual_method，不把calculate改名真太阳时 |
| D2 | birth.place.tz必须IANA；clock_basis显式提供 | 新增birth.location.tz、birth.clock_basis资料确认；缺项MISSING_INPUT及确认卡，禁止默认中国时区 |
| D3 | time_basis只处理reported；倒推冻结隐藏 | 未知/区间走旧calculate采样，显示“旧口径，未做真太阳时与交界提示” |
| D4 | time_basis归属在顶层；四新工具在scope；预览是第三种结构 | 新增verify_p8_document，验证归属、revision、有限JSON、内容hash及可信产物来源；不能套旧五键校验 |
| D5 | 下方Pointer表；工具aliases.path与预览aliases.ref不同 | 服务端逐轮重登记{document_id,pointer}，max10；不能复制样例c1/r1 |
| D6 | 38条rule_assessments，rule_hits只met=true | 新路只用真实命中；旧KnowledgeRegistry仅旧路 |
| D7 | worker失败折叠；详见错误表 | Pydantic前置校验，返回固定安全错误，不透传stderr |
| D8 | window原生≤366天，分页≤31；worker45秒 | Agent上限92天，实测92>30秒则62；page31，显式range与deadline |
| D9 | almanac(date)采用sect1历法库黄历输出 | 仅显式黄历意图暴露；time_context摘要不替换 |
| D10 | daily_transit(natal,date,orb_degrees=2) | 日运用此入口；chart_compute.scale=daily仅指定日交互表 |
| D11 | western_timing保留独立研究接口 | 本批推运/回归UNSUPPORTED，不猜回归地点 |
| D12 | chart_skill(system,topic)，本地枚举白名单 | 注册工具；同轮成功chart_compute后可见；只读技能可在隐私模式 |

## 已确认资料 → 原生请求

主线从授权档案读取，模型不能提交birth或consent。所有字段都需同一owner/subject/revision。

| 确认档案字段 | time_basis请求字段 | 四工具natal字段 | 缺项行为（主线） |
| --- | --- | --- | --- |
| birth.solar_datetime | birth.date + birth.reported_time，保留秒 | 相同 | MISSING_INPUT；不是用当前日期 |
| gender | birth.gender=男/女 | 相同 | MISSING_INPUT |
| birth.location.lng/lat | birth.place.lon/lat | 相同 | MISSING_INPUT；西占lat绝对值<90 |
| birth.location.tz | birth.place.tz | 相同 | MISSING_INPUT；UTC偏移不可代替IANA |
| birth.clock_basis | birth.clock_basis=clock/standard/unknown | 相同 | MISSING_INPUT；不能默认为clock |
| birth.precision | birth.precision=reported | 相同 | 未知/区间返回旧路，不能伪造reported |
| 受信归属/修订/操作ID | 顶层owner_user_id/subject_id/revision/operation_id | natal顶层同四项 | AUTH_SCOPE_ERROR或确认资料 |
| 主线Clock目标日 | 顶层as_of_date | daily.date / synastry.as_of_date / window.range | 要求显式日期，不依赖宿主时区 |

阿远映射：1994-03-12T08:20:00，男，104.07/30.67，Asia/Shanghai，clock，reported。
样例出生均为合成；mainline需补真实用户的IANA和依据确认，不能从该示例推断默认值。

## Pointer提升表（主线实施；不重写原生结果）

| 原生字段/根 | 登记到time_basis文档的Pointer |
| --- | --- |
| charts[i].data.p8.rule_hits[j].evidence_paths[k]中的/data/X | /charts/i/data/X |
| charts[i].data.p8.rule_assessments[j].evidence_paths[k]中的/data/X | /charts/i/data/X；false仅日志，不登记r |
| charts[i].ziwei_column的飞化Pointer | 已为/charts/i/ziwei_column/...，禁止二次提升 |
| boundary_alerts[j].evidence_paths[k] | 原样解析time_basis整文档；不要加/data |
| 四工具aliases.c/r[].path | 以各工具自身document_id为根，原样 |
| 预览aliases.c/r[].ref | 使用ref.document_id与ref.path；不是原生path结构 |

路径必须严格解析并校验同一归属/修订。hash只是内容摘要，不是签名或来源认证。
time_basis目前无tool-内容document_id；由主线校验可信worker来源后生成规范ID并存文档。

## 错误分层（四工具分别列示）

| 工具 | worker/transport真实可见错误 | 主线前置校验与安全响应 |
| --- | --- | --- |
| daily_transit | RuntimeError chart_engine_failure/missing_chart_dependency/chart_output_limit_exceeded；TimeoutExpired；JSON解析/有限数校验错误 | 严格日期、orb有限0..10、已确认natal；缺资料MISSING_INPUT；归属AUTH_SCOPE_ERROR |
| window_search | 同上；window_*细码不会自动跨worker保留 | purpose六枚举、严格range且inclusive≤Agent上限、offset非负整数、limit1..31；INVALID_ARGUMENT |
| almanac | 同上；almanac_*细码不会自动跨worker保留 | 严格1901..2099日期；INVALID_ARGUMENT；不需要私人出生资料 |
| synastry | Core预检ValueError前缀CONSENT_REQUIRED/AUTH_SCOPE_ERROR；worker失败同上 | 先查24小时一次性授权账本，再查双方准确资料、kind及orb；缺授权CONSENT_REQUIRED，缺资料MISSING_INPUT |

本线synastry(request)只有精确字符串consent=user_confirmed才继续计算，缺失/False/true都拒绝；
这是内层护栏，不是用户确认记录。主线须返回{ok:false,code:CONSENT_REQUIRED}并发确认卡。
双方修订、kind、owner、确认卡operation_id绑定，24小时、uses_left=1；撤销/改修订/换kind失效。
不写记忆/档案/AboutMe，不进入反思；forget撤销授权。模型参数不提供consent或birth。

### 本机区间观测（2026-10-26，n=3，各次重新准备本命）

| inclusive天数 | 三次耗时（秒） | 最慢 |
| --- | --- | --- |
| 31 | 4.427988 / 1.244026 / 1.219402 | 4.427988 |
| 62 | 2.188611 / 2.243598 / 2.226765 | 2.243598 |
| 92 | 3.220503 / 3.238145 / 3.232991 | 3.238145 |

据此建议Agent上限92天、每页31，不触发42号“92天超过30秒则降62”规则。
证据：[原始观测](../evidence/P8/wiring-window-performance-20261026.json)。
包括全日期计算/排序/分页/证据；不包括Core进程启动、JSON传输或HTTP，不是45秒超时的服务保证。

## 白话模板与技能索引

skills/boundary_messages.render_boundary(document,rule,evidence,used_pillars={"hour"},brief=False)接受主线已经登记、
同一可信文档内的别名行：rule={alias:rN,path,evidence_aliases:[cN,...]}，evidence=[{alias:cN,path},...]。
预览ref需先映射到该文档，不能把整预览当原生根。函数重新解析rule和证据Pointer，拒绝false/无来源/假引用。
hour_branch、late_zi_day、zi_midnight、jie_month、eot_implementations均使用实际秒数、具名流派和实际比较柱。
只在used_pillars与实际比较差异相交时返回提示，否则返回None；未使用受影响柱时不打扰回答。
午夜两侧同柱且无具名流派对照差异时不造另一柱；均时差差异可能影响任意柱，绝不写死时柱。
返回text、affected_pillars、school、source和原别名。brief=True只短引，是否已完整提示由主线会话状态决定。

skills/wiring_index.skill_index()仅返回32章元数据和精确体系/topic配对，不载入全文；
catalog.json每章wiring_applicability标记何时使用。加载正文仍用chart_skill，5500 UTF-8字节保守预算不变。
冻结倒推章只能诚实拒绝；西占推运/回归章节是教育内容，不解锁本批UNSUPPORTED工具。
枚举和场景另导出samples/p8-skill-index.json，主线不可把不同体系的topic交叉组合。

## 主线需要调整的已有模块

依据42号审计的文件定位，合入时重新核对实际路径/签名：
application/agent_tools_charts.py（路由/工具定义）、application/charts_service.py（验证/产物存储）、
domain/consultation.py（确认资料字段）、cached_chart/chart_lineage所在模块（document+Pointer），
Agent工具可见性装配（metaphysics_intent优先synastry>window>almanac>daily>none，最多一个新工具）。
意图只来自用户原话，不接受引文或否定意图。四工具在危机/隐私模式隐藏；每轮工具总数≤15。
必要时calendar_lookup/set_reminder降级，主线跑core29。边界提示同档案版本/会话首次完整、后来短引；
去重状态由主线保存，不能在本线静态函数里维护全局私人状态。

## 三份端到端合成材料

复用samples/ayuan_bazi.json、ayuan_ziwei.json、ayuan_astro.json：输入为文件request，
原生输出在documents[].payload，展示引用在view，实际c/r对应同一文档Pointer。
它们是实际计算→合成装配→引用验证的材料端到端，不是Agent/HTTP/授权账本端到端。
三体系既有输出保留；astro示例研究用timing字段不代表本批允许注册该工具。
主线装配请从真实文档重新登记别名，不能照搬演示编号。
samples/p8-wiring-cases.json逐份列出已确认资料映射、归属修订、预期document_id；
test_p8_wiring_pointers.py校验三份输入映射、源hash、全部assessment证据根及true命中引用。

## 验证与待核

本次定向/全量证据在日报和ExecPlan增补；完成前不写就绪。流派原刊未核项仍见原技能与来源表。
无迁移、无新增依赖。若回滚只撤销本材料提交，不能删除用户档案或改变v3。
