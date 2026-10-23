# 旧流式 core3 主体接线约束

`stream_outbox_v2` 在领取和发送前都要求完整 core3 payload 的 `meta.subject_id` 存在，
并与可信 host 绑定的 `StreamScope.subject_id` 完全一致。不能缺失或跨 subject；旧 scope/run_id
及 payload hash 自洽仍不足以授权投递。错误主体使用既有 `validated_subject_mismatch` 原因码拒绝。

host 应从当前权威 run 与来源投影取得主体，保留完整 `validated_payload`、dependencies、
manifest、来源 epoch 和两次 freshness 核验。历史结果缺少主体时必须权威补投影或拒绝，不能从当前请求猜填。

此补丁没有查询 PG、发送卡片、自动迁移历史数据或放行未知状态。真实锁行/CAS、主体授权、
先持久化 dispatched 再传输和平台对账仍由主线接线及隔离实库验收负责。
