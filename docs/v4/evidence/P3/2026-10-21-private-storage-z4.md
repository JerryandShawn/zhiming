# 无痕存储 / Z4 独立服务证据

本片结果与限制见 `execplans/P3_private_threads_2026-10-21.md`。使用本机隔离PG15.19，测试不依赖本机默认时区。39项线程/确认/P2隐私目标通过；普通history过滤补充后4项私密线程复测通过，ASGI渠道history另1项通过。39包含此前的4和12等测试，不能简单相加。

断言实际数据库状态：无痕原话/回答不进普通history、来源快照、FTS和飞书history；长期save_fact、grant_authorization、create_case拒绝私密来源；跨owner/subject拒绝；原话ID不能换内容；活动延长24小时，到期清空run/step/event/缓存并撤销lease，保留人生原话和其他owner。提醒先问一次、同意后才保存且无thread/source/run链接；不明确和拒绝均不保存，旧原话变化或助手回答不能授权；7天清理必须有matching sent收据，清payload而保留收据。

代码为应用/存储服务，**Runtime/工具桥接/对外确认API/送达hook/到期worker尚未接入**。所有“送达”用数据库合成行，不构造sender、不发送飞书。私密读取端复核发现并补两条旧旁路，不把单一FTS空结果当全部隐私隔离证明。未启动默认v4路由。

来源：用户28 Z4和P3 M5；没有新增依赖/迁移或服务器动作。实际模型请求0、飞书发送0，PR保持草稿。锁内Starlette anyio弃用告警保留，未升级依赖或屏蔽告警。
