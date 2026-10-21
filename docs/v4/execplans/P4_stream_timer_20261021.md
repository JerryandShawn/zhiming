# P4 M2b：独立定时刷新与有界数据库候选

本ExecPlan遵循`.agent/PLANS.md`。Progress、Surprises & Discoveries、Decision Log、Outcomes & Retrospective持续更新；时间为北京时间UTC+08。当前基底`v4/p3-wire-p4-20261021@0af15deb17c19f7d7d0a983b69038764765903b2`，tree`49fcf1c2`；这是已提交M2a，并非完整P4。候选默认关闭，P3 X03/旧DOM/encoder及B1 No-Go仍保留。

## Purpose / Big Picture

用户看到不足40字的模型片段后，即使供应商暂时不再发片，独立调度也应请求刷新，不等待下一片或模型结束。本片复用模块原`poll_delta`，保持冻结events_v1，不改原12源。遇到取消、撤销、旧租约、PG锁竞争或超时则停止旧调度，拒绝继续final；不会为了完整输出强发已失效缓冲。150ms是调度与原纯核的目标边界，本机实测延迟另给证据，不能从SQL超时推出网络黑洞下的绝对提交时限。

## Context and Orientation

工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`。复用`run_event_stream.ModelDeltaStream.begin/push/finish`、`run_event_stream_state.StreamState._proof/begin/commit`、原`streaming_candidate.coalescer.feed_delta/poll_delta/flush_delta`、`repositories.run_event_log.append_event`与Journal/RequestLedger真实性门。M2a已有15新增和41相关窄目标，旧unfinished generation保留原件并拒绝新流；这条行为不改变，不增加恢复旁路。

现有`PostgresRepository.transaction(owner)`先以20秒pool timeout取连接，再等待owner advisory锁；调用方之后才设置SQL timeout已经太晚。因此新增仓储级有界上下文，而不改通用transaction或让应用任意碰`repo._local`。M3代理独占hub/listener/service/thread_events/web，不能交叉编辑。

actor指一个唯一拥有buffer、metadata和generation的工作线程。producer只交付最多2个命令并等待有界确认；timer和producer不会各持一份可提交buffer。actor等待队列时用单调时钟计算deadline，原纯核仍使用可冻结UTC Clock做时间判定；这两个时钟的测试分开。

## Progress

- [x] (2026-10-21 10:22 +08:00) root批准M2b独立片，M2a已原生提交并逐字节核12原件；完整读现stream/state、repo事务、control与模型/评审顺序，建立本计划。
- [x] (2026-10-21 10:27 +08:00) 新仓储有界上下文、单actor与ModelDeltaStream/StreamState委托；初组pure/PG事务/原Runtime22通过。
- [x] (2026-10-21 10:28 +08:00) Runtime仅构造行传已有control.cancel_event，写事务严格复用turn_sources/current_source_ids与prepared.versions；真实依赖版本变而lease未变、取消、撤销、换lease均能由timer唤醒静默端口。
- [x] (2026-10-21 10:35 +08:00) 保留两次真实失败：已知actor错误被provider unavailable遮蔽、未确认timer写窗口逃逸partial；root批准最小facade/inflight门后，最终37目标通过，0fail/error/skip。
- [x] (2026-10-21 10:36 +08:00) 原M1/Runtime/回放/无痕/inbox明确5文件41通过；全程单窄进程串行，已释放槽。Ruff/format/AST/400-60/diff通过，原12来源hash不变。
- [ ] root复核并小提交；默认关闭，不部署。

## Surprises & Discoveries

普通工具、提问、选项、review/reset均在真实模型`finally finish`之后，先复用这一已证边界，不扩大ToolBatch或review接口。失败finish若再取actor/buffer锁或等待PG确认，可能使取消被旧刷新拖住，因此必须先置停止标志并立即返回，不能join。

SQL statement_timeout/lock_timeout可以限制服务器语句/锁等待，pool timeout限制本地取连接等待；同步客户端在网络黑洞或COMMIT未知结果时仍可能阻塞。daemon只避免阻挡解释器退出，不证明连接回收或安全结束。发生确认超时后调用方停止发布，旧worker最终返回必须丢弃其内存并归还连接；真实网络黑洞仍明确未验证。

10:28首组真实timer测试5过1失败：owner try-lock失败已设置actor.failure，但静默port抛ModelUnavailable后被原Loop转为可finalize outcome，失败finish只stop而未传已知actor错误，导致partial逃逸。10:33另一个窄反例真实复现未确认timer写：在timer提交入口注入阻塞/失败，provider独立故障时failure尚未赋值，也会发布partial。没有修改Loop/U41或放宽原断言；在facade保守拒绝已知失败与未确认在途写。

## Decision Log

2026-10-21 10:22 / root：只新增`application/run_event_stream_worker.py`和`repositories/streaming_transaction.py`，小改ModelDeltaStream/StreamState；有界pool、SET LOCAL timeout、pg_try_advisory_xact_lock与repo._local共享必须封装在仓储。通用repo.transaction、模块原件、Schema/依赖/迁移均不改。

2026-10-21 10:22 / Codex实施设计：actor独占状态；队列maxsize=2、每次producer最多一条待确认，纯buffer/队列锁均不跨PG或网络。失败stop只置Event、尽力放入唤醒命令，不join、不等待ack；正常finish只等待有界ack，超时fail closed。PG取消的线性点仍为真实cancel事务，不能撤回其之前已经提交的事件。

2026-10-21 10:22 / root随后批准：异步timer失败设置已有RunControl.cancel_event，仅在Runtime构造ModelDeltaStream的一行传入该event；确认_cycle已有该局部。每次写事务复用现有turn_sources/current_source_ids与prepared.versions检查，不能只信内存step或旧来源摘要。

2026-10-21 10:29 / root批准已知失败传播：失败finish先stop，再无锁读取固定worker.failure，若存在则抛CoreError沿原Loop无效依赖路径拒绝partial及U41 fallback；不等PG/ack、不join。真正供应商ModelUnavailable但actor没有失败/在途的旧行为保留，并有实际Runtime对照。

2026-10-21 10:34 / root批准未知写门：每次begin/commit前先set write_inflight，再检查stop；finish先stop再无锁读failure/inflight，未知结果立即拒final。worker错误先置固定failure再clear marker；若finish先看false、worker晚set，后者检查已stop而绝不开始PG。marker不冒充成功ack，覆盖真实commit和事务外callback直至返回，防止final后晚到旧delta。callback本身已开始的外部行为不能撤回，当前HTTP走PG读取，本片不声称能取消任意阻塞callback。

## Outcomes & Retrospective

已实现单actor/queue<=2、150ms目标的独立deadline调度、有界PG获取/锁与原Clock纯核；真实Runtime静默端口在下一片之前出现持久delta。最终37目标/11.82s与相关41/15.98s通过，详见`docs/v4/evidence/P4/2026-10-21-stream-timer.md`，两次实质首红原始产物保留。真实版本/来源/租约门、未知提交拒final、callback顺序与0join反例已覆盖。M2a40字、strict bool默认关、来源原件及unfinished fail closed均保留。同步PG黑洞、COMMIT未知的资源上界、完整恢复/HTTP/脚本/生产ready仍未验，不以本片窄绿宣P4完成。

## Plan of Work

仓储`streaming_transaction(repo, owner, stopped)`先拒绝已有外层threadlocal连接，再限时从原pool取连接；进入真实事务后先设置局部statement/lock timeout，再用非阻塞owner advisory锁。设置`repo._local.connection`仅在该线程上下文内供原Journal/ledger嵌套服务共享；finally恢复原值，异常事务回滚、连接交回pool。既有owner/subject/lease/epoch与真实源检查仍在获得锁后的事务内，退出前再检查本地stop。不会向错误或日志返回DSN、正文或原供应商异常。

worker开始时由actor完成state.begin，保存唯一buffer。push用原feed_delta、timer用原poll_delta、正常finish用原flush_delta；任何metadata/offset更新都先真实PG commit成功才采纳到内存。deadline只从当前非空buffer原起点对应的等待间隔安排，queue读取时独立超时醒来；buffer空则不定时轮询。异常记录固定领域错误并设置现有取消event，不携私人正文。callback在事务外执行且仍处于inflight内，回调完成后才能确认命令/允许final；失败stop不等待它，保守拒final。已stop/cancel时跳过尚未开始的callback；任意已开始阻塞callback无法撤回，不能拿daemon声称解决。

锁次序为：短队列操作结束→set inflight/核stop→50ms pool连接→真实事务→100ms statement/25ms lock timeout→try owner advisory→原Journal行锁/来源/ledger→事件与metadata→commit→事务外callback→clear inflight→命令ack。没有同时持有buffer锁和PG锁，stop不反向获取这些锁。只有actor写buffer；producer和timer不会竞相CAS两份状态。外部租约/generation/撤销变化仍由真实PG门拒绝。normal ack上限0.75s，超时设置失败/取消并阻止继续final；这不等于证明网络黑洞下worker已经退出。

## Concrete Steps / Validation and Acceptance

获分配的单窄位下，通过root安全runner运行明确文件，固定本机隔离PG、清凭据/追踪、TZ=Asia/Tokyo。先新的纯worker和仓储/实际Runtime timer文件，再M2a及明确M1/Runtime旧文件；禁止整个目录宽测。后续记录每条实际命令和原始JUnit/hash。

行为门对应P4事件X08、真实取消X04及撤销F03/F04边界：冻结Clock的149/150ms原算法与受控scheduler目标，不能混成实测延迟；真实静默合成port在下一片前PG出现不足40字片段；owner锁被另一连接持有时限时拒绝且0旧正文；pool耗尽/语句锁等待后的threadlocal恢复与实际连接返还；取消/来源撤销/epoch或租约改变后旧timer拒发；失败finish对阻塞worker立即返回、无join；正常finish确认超时不能final；review reset之后没有晚到旧delta。原M2a15目标和相关41目标的旧断言保留。

## Idempotence and Recovery

本片不迁移、不删数据；稳定key仍为真实epoch/model step/generation/字符offset。确认失败或COMMIT未知保留现PG记录并停止继续流，禁止凭新generation掩盖恢复。flag关闭只回原事件路径，不清ledger/metadata。取消前已提交事件仍遵原隐私撤销清理；本片不从buffer/operation重造被清除正文。

## Artifacts and Notes

计划为本文件；证据`docs/v4/evidence/P4/2026-10-21-stream-timer.md`包含实际命令、测试时段、安全raw日志/JUnit/hash与两次实质失败。此片只本机离线合成供应商与真实隔离PG，不证明Linux/真实模型/服务器。

## Interfaces and Dependencies

新actor仅是内部API；ModelTextStream协议不变。无新依赖、迁移、公开Schema/API、模块源或前端变动。timer/hub分工仍独立。同步PG网络黑洞、COMMIT未知的严格截止与完整恢复仍未验证，不承诺全边界2秒。

## 修订记录

- 2026-10-21 10:22 +08:00：root批准M2b后建独立计划，列actor唯一状态、锁顺序、连接归还、取消/来源事务门与网络黑洞限制，避免把M2a成功扩称完整M2。
- 2026-10-21 10:36 +08:00：记录真实timer首红与未知写竞态、root批准的facade/inflight最小修复、最终37/41窄目标及callback/资源未验证边界；保留原M2a与P4未验门。
