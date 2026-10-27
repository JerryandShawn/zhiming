# 第三批P4二选一建议（模块线，一页）

观察时间：2026-10-27T09:17:29.820656+08:00；只读对照主线树zhiming-v4-p3-wire-p4，HEAD 9b4aa474bd1837702e8229284226921e04002136。本建议不是运行验收，也未改主线。

**建议选主线P4作为唯一事件存储/HTTP续传权威，只吸收模块纯逻辑。** 另一选项是整体采用模块PgEventStore并替换主线读写链；这会重复owner/run事务、retry_epoch、操作幂等与删除元数据，需要重接已有路由，因此不推荐。最终选择由主线记录Decision Log。

| 对照位置 | 已观察行为与适配决定 |
| --- | --- |
| 主线repositories/run_event_log.append_event | 调用者权威事务中再次锁run，检查epoch/subject/保留状态；幂等操作含epoch；旧事件被清除后拒绝重建；插入与pg_notify同事务。保留它，不接模块第二套PG表/序号。 |
| 主线adapters/run_event_follow.RunEventFollow | 使用授权RunEventReader分页；通知只唤醒、不推进游标；15秒心跳、断连关闭订阅、无通知时轮询。复用同一follow给冻结v1与legacy编码。 |
| 主线application/run_event_read.RunEventReader | 每页重新核owner/subject/thread，按owner/run/seq取行，跳过已清正文但推进扫描游标；缺失游标查删除元数据。模块resume纯数字解析不能取代这里的撤销/保留证明。 |
| 模块streaming/coalescer | 可复用DeltaPolicy默认40字/150ms及注入Clock；generation变化拒绝旧writer，text_reset丢弃旧缓冲。适配EventDraft到主线冻结events.py后，由原事务分配seq，禁止模块预分配。 |
| 模块streaming/cleanup | 仅输出24小时后text_delta清理计划，包含commit revision/seq/指纹；主线现有执行器复核后执行，保留撤销墓碑/游标证明，不另注册第二任务。 |

适配顺序：主线确认冻结v1字段→如有需要移植coalescer纯策略→逐事件校验并在原事务写入→统一follow读取→legacy桥只变编码。不能因两个实现同名就整目录覆盖；模块EventStore、模块编码和主线run_event_log不应同时成为权威。

需要主线验证：同一owner/run断线无重复缺字、错误/未知游标拒绝、清理后合法空洞与缺失前缀、撤销不重建正文、retry_epoch旧writer拒绝、text_reset后旧delta拒绝、关流式兼容旧网页、LISTEN连接回收。HTTP路由、Agent、LISTEN启动、取消与清理任务均归主线；本轮未运行产品链路、PG集成或真实首字性能测试，真实模型/服务器请求0。
