# P3 私密保留维护的生命周期安装证据

2026-10-21 00:49 北京时间。本机 Windows 隔离 PostgreSQL 15、合成模型；没有服务器访问、真实模型请求或飞书发送。本片在 `4d89324` 的 API 安装候选后独立增加保留策略维护，未改变普通 v3 默认选择。

新增 `application/maintenance_schedule.py`，只在 monotonic 到达60秒窗口时调用 `PrivacyMaintenance.tick(limit=50)`；先预约下一窗口，长任务跨过60秒也不会并发重入。失败只记录固定 `PRIVACY_MAINTENANCE_FAILED` 和计数，绝不记录异常正文；保留 last_error_code 可观察，下一分钟再试。旧 Web worker 用 `asyncio.to_thread` 调用节流器，不把每2秒轮询变成每2秒全量清理。

验证：`test_maintenance_schedule.py`、`test_privacy_maintenance_pg.py`、`test_privacy_maintenance_boundaries_pg.py`、`test_maintenance_lifecycle_pg.py`、`test_thread_routes_pg.py`，**15 passed，5.22秒**。唯一警告是既有 Starlette TestClient / AnyIO 弃用提醒。新增4文件 Ruff E/F/I/B/UP/SIM（120）和 format 通过。

覆盖精确分钟边界、limit50、失败不泄露/不高频重试、跨分钟并发不重入；真实 PG 覆盖同实体ID不同owner不误删、31天仍running的步骤和lease保留、实际旧Core3 LangGraph合成终稿与私有步骤保留、无痕24小时到期、终态v4私有步骤30天清理但公开final保留。生命周期用真实旧v3合成运行证明：维护失败后服务仍产出验证core3终稿，错误仅固定code可见。

没有新增迁移。节流器是单Web进程内保护，PrivacyMaintenance 的PG行锁和幂等决定实际写入安全；尚未验证多服务器部署、长期定时运行、模块线SSE24小时清理或生产负载。撤回该片可移除 worker 的维护实例与调用，业务终稿读取不变。
