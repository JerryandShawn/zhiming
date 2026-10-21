# P4 M3首片：有界提示Hub与单LISTEN的真实SSE消费者

本ExecPlan遵循`.agent/PLANS.md`；所有记录北京时间UTC+08，四活节持续更新。独立目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，已提交M1为95df0f9、Draft PR14；本片与M2a并行，绝不改其Runtime/Loop/stream/state/12原纯核文件。默认关闭的可信bool候选开关只能来自create_app构造，HTTP/模型不能开启。root于10:15:35释放第4测试位，本片之后只用一个窄pytest进程串行验证。

## Purpose / Big Picture

当前SSE已经从真实PG读取冻结events_v1，但每150ms轮询。M1事件同事务发送mj_run，本片让实际Web lifespan只持有进程级一条专用LISTEN连接，通知唤醒真实HTTP订阅者，正文仍经原RunEventReader授权回读。每订阅者队列只保存一个seq提示，调用event loop之前先合并，慢浏览器不会把模型线程、待loop回调或正文缓存拖成无界。通知丢失/重连仍靠原150ms PG补读，断线退订不取消run。

## Context and Orientation

已完整读`adapters/thread_events.py`、`thread_routes.py`相关GET与`web.create_app`/lifespan/v4旧stream调用、`RunEventReader`、M1 append_event、repo pool/transaction、dispatcher现有通知桥及psycopg已锁notifies实现。复用RunEventReader.authority/validate_cursor/page、冻结encode_sse/heartbeat与M1提交后pg_notify；不改事件Schema/core4，也不绕owner/subject/thread/epoch/来源撤销/取消现门。M2a作者已确认不写本片文件，HTTP只读M1实际事件，不需要触碰ModelDeltaStream。

hub只持真实repo/app scope、owner/run标识、loop、一个整数Queue与待调度标记，无正文/工具结果/回执/lease/token。channel只有mj_run，payload从最后冒号切run_id和seq，malformed/unknown run直接丢弃，不作权限推断。dispatcher的mj_run_queued/cancel连接不复用，不在本片改变取消执行控制。

## Progress

- [x] (2026-10-21 10:05 +08:00) 完整只读HTTP/PG/事件/模块接口，M2a作者确认hub/listener/thread_events/web所有权无交叉，已给root接口和具体文件。
- [x] root批准三新application文件、thread_events/web最小真实接线、默认关闭可信bool、现cursor门保持，先编码/静态；当前不授权pytest。
- [x] (2026-10-21 10:25:11 +08:00) 三新application文件与thread_events/web最小接线已验证，默认关；真实应用开启后仅一条mj_run LISTEN，两个独立HTTP app event loop共享连接。
- [x] (2026-10-21 10:25:11 +08:00) 最终四个独占新目标28 passed/8.72s、0skip/xfail/warning；18纯边界+2真实PG listener+8真实socket HTTP/PG。日志`private/p4-event-hints-20261021/final-target.log`。
- [ ] M3后续精确游标/墓碑/after别名、M2定时flush与Runtime联合链、旧DOM/完整X08/清理及P4全验收仍未完成，不由本片数字代替。

## Surprises & Discoveries

模块没有hub可复用，M2a提取的12源纯核也没有网络/连接管理。其真实flush仍只调用M1 append_event，由PG commit交付通知，因此本片只消费NOTIFY，不加尚不可靠的“savepoint即提交”本地publish。所有同进程/跨进程事件都由同一个真实commit来源唤醒。

Queue(maxsize=1)本身不能限制无限call_soon_threadsafe；publish必须在短锁内先合并pending最高seq，只从未调度到已调度时加一个callback。未知run不能创建cache；读端不能把通知seq写进cursor，伪造高seq也不跳过真正较低的后续事件。

现RunEventReader.validate_cursor只拒大于当前max，而非精确存在行/清理墓碑；此首片按root保持原门。after查询别名、精确游标/tombstone、M2 timer/reset/旧DOM/清理与完整X08仍未完成，不把此M3片当P4验收。

首次新PG测试使用相对导入而目录没有包，collection报1错误，未执行测试；改成已有tests命名空间绝对导入。首次4条HTTP测试返回502（tool chunk88069e、4 failed/10.55s），请求URL均为127.0.0.1临时端口，但httpx默认读取Windows用户代理注册表；测试未注入代理，代理环境变量列表为空。只读无请求诊断证实默认HTTPProxy、`trust_env=False`为ConnectionPool；未输出代理地址/凭据，也没有再次发代理请求。最终客户端统一`trust_env=False`，子进程只用明确本机PG、无HTTP，有限环境清凭据/PG隐式变量。原失败保留，不能把最初误路由说成全程网络都直连。

## Decision Log

2026-10-21 / root：仅新增application/run_event_hub.py、run_event_listener.py、run_event_service.py；最小改adapters/thread_events.py和web.py，独占新专属测试/本计划/证据。不碰M2文件、M1写端、旧断言、Schema或其它树。四宽结束释放slot后才pytest。

Codex实施规则：默认关闭可信create_app(...,event_hints=False)。同进程一个broker，规范DSN相同的多个可信app共享一条LISTEN，冲突配置显式拒绝，不悄开第二连接。活跃app scope上限16、总订阅256、每app订阅128、每run32，无无订阅高水位缓存。每sub一个Queue(maxsize=1)，整个app仅一个待loop pump；2000次退订/重订不能在暂停loop里累积2000个callback。closed对象晚callback立即退出；卸载最后app先关连接/线程再允许新broker，避免关闭窗口里短暂双连接。owner仅订阅scope标识；同run通知只促各自PG回读，hint不作owner授权，也不声称per-owner限额。

Hub只提示，所有SSE事件来自reader.page真实DB；先鉴权/游标，再注册订阅、补发并追赶。完整分页优先于等待，擦除行仍按真实seq推进，终态由reader实际final/error修复路径后完成；不能凭提示或内存状态关流。真实HTTP断线与ASGI取消在finally移除queue/loop，不触发run cancel；主动cancel原路由不改。

## Plan of Work

新Hub在producer/listener线程publish时仅更新已有订阅的pending seq，在call_soon之前合并；loop callback非阻塞put/替换唯一queue项。消费提示只触发PG补读，绝不改cursor。读完所有可得页后才等待hint或150ms兜底，空闲15秒冻结心跳，不落库。拒未知通知、重复/倒序/极大seq不会授权正文或创建缓存。

新Listener持专用autocommit连接，固定LISTEN mj_run、短通知等待、有限连接超时和有上限退避；连接断开只记固定安全code/饱和计数，不输出DSN或PG异常文字，不阻断旧v3 worker。关闭设置stop、关闭自身连接并有界join，不能泄漏后台线程；不得关闭业务repo pool。共享Service负责进程注册/引用计数和每app scope清理。若显式启用却遇不同DSN或app上限，在启动阶段明确失败，不静默创建多个连接。

Web只有可信开关为True才在lifespan安装Service并启动listen，关闭时释放；开关False无新监听连接，保留当前行为。thread_events从可信app.state取当前repo匹配的service，任何HTTP header/body/query不能替换它。首次reader已授权后注册提示，再回读PG以覆盖建立订阅/首次快照/并发提交竞争；Response层及生成器finally都释放订阅，避免断线未启动body遗留。

本片所有应用缓存/loop回调有界；不把libpq/OS或代理层缓冲误说为已测固定内存上限。真慢HTTP客户端的正文仍由PG按分页取出，本片不创建另一个事件正文队列。旧v4 POST stream与GET两入口共用event_response，默认v3与旧SSE协议转换仍原样，不能据此说旧DOM逐字已兼容。

## Validation and Acceptance

root授slot后仅一窄pytest进程，清供应商凭据/关闭追踪，PG本机隔离、HTTP只能127.0.0.1，TZ=Asia/Tokyo；无真实模型/飞书/服务器/WSL/Docker。对应07 X08及F03/F04/X04约束，冻结事件及旧断言不改。

纯目标：总/perrun/每app订阅/app数量容量拒绝，loop静止时大量publish仍每app≤1callback、每sub≤1queue项，无unknown cache；callback晚到/loop关闭/幂等unsubscribe释放；多线程并发提示只合并seq、fake超高seq后真实较低事件仍可读。

真实PG：多订阅仅一LISTEN连接，嵌套事务commit前无唤醒/rollback无事件，commit才唤醒；连接断开后真实重连与fallback补足、同DSN多app引用/最后关闭释放，冲突DSN不另开。观察本片独立application_name计数，不混dispatcher连接。

真实HTTP+PG：实际GET和可信lifespan开启消费者，用socket Uvicorn/httpx.stream逐帧读，不用缓冲ASGI替身；订阅前/中/后提交、>256及>1000行与终态分页、Last-Event-ID无重复/漏、两owner与不同run混通知、假高seq/无row、撤销清空/取消error、断线退订不cancel。独立Python进程运行真实ScriptedPort/AgentRuntime或M1受信事件写端，通过同PG通知使Web读取已提交行；不以手调用Hub证明跨进程。用可受信测试等待间隔/ready信号分离通知与轮询证据，不靠固定睡眠伪造唤醒。

## Idempotence and Recovery

通知可以重复/丢失/乱序，实际seq/cursor以PG为准。Listener重连不重启run或重放业务工具；断开订阅不删事件。重复关闭/sub释放幂等、最后service关闭清除所有scope引用，不保留owner正文或历史高水位。开启候选不改变写端事务/事件操作身份；回到默认轮询不删事件/ledger。

## Interfaces and Dependencies

实际接口：RunEventHub.open_scope(loop)→opaque token；subscribe(scope,owner,run_id)→Subscription(wait,close)；publish(run_id,seq)仅内部；EventListener.start/close/ready；acquire_event_hints(repo)→单app lease(scope/subscribe/close)，内部全局单broker。内部标识与诊断不进公开Schema。Web新增可信bool构造参数，无环境/HTTP任意path/DSN覆盖开关。新依赖/迁移0，新增与本片重构源码≤400、函数≤60，旧web仅小diff。

## Outcomes & Retrospective

首片实际消费者与资源门已由28个新目标验证，详见`docs/v4/evidence/P4/2026-10-21-event-hints.md`。真实跨进程生产者是已持久lease验证的M1 RuntimeEvents，不是手工调用Hub，也不是完整M2a AgentRuntime逐字生成证明。真实终止自身listener后暂停重连时，HTTP靠原150ms PG兜底读到事件；恢复后只一条新连接。3秒join是app卸载时线程检查，不是运行取消时限，亦不冒称任意网络黑洞有硬关闭期限。默认关闭、没有数据库迁移，root统一提交/推送，PR保持Draft；P4整体仍未验收，原错误与未完成游标/联合链保留。

## 修订记录

- 2026-10-21 创建：root已批具体排他文件，M3默认关候选、单process监听/有界hint/真实SSE消费者/资源清理与真实PG/HTTP验收门；四宽期间先实现静态、不pytest。
- 2026-10-21 10:25:11 +08:00：记录获窄位后的28项最终实测、最初导入/注册表代理502及准确默认关闭/资源/授权边界，冻结M3首片，不扩游标或M2范围。
