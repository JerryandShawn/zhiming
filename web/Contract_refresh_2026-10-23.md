# 10-23 前端契约刷新（只读，未接线验收）

北京时间21时，完成当日一次授权GitHub fetch；没有合并、切换分支或修改其他工作树。机器核对见 `web/evidence/2026-10-23/contracts_refresh_checks.json`。

## 线程接口

`origin/v4/p3-agent-runtime` 从 `a83ca8b719597799600a1715e0b097c5b2219e1d` 更新至 `27b8af95a2a17d548b78ac25c9941c24b5cc85fd`。api_runtime索引、thread_runtime_api、thread_routes、根适配器web.py、thread_events、run_event_read及事件/core4 Schema共九个blob完全相同，整个mingjing_core树无变化。当前本地事件夹具仍为同一个c84b89f3 blob。

现有DTO A纯请求/202回执候选无需因换头改规则，但**尚未正式迁入或验证**。独立复核未发现新增阻止项。B必须核人物与operation归属、禁止默认重定向；损坏202、500或媒体类型错误不能证明零写，保留原request_id。现有B草稿已有出站人物校验与redirect:error，迁入后仍要验证，不以阅读代替测试。C的缺号、坏游标、取消与retry epoch边界按Thread_runtime_integration_notes保持。

## 整理接口

模块线从 `ebfa22f8f7c59e486c6632035ae6bc8307f0f438` 更新到 `2f01b843d6661b76799ce09c285171b6e5010dc2`。独立逐blob阅读确认README、Q1/Q5指南、changes/_change_values及proposal/v2契约不变。新supplement_v2、partition_context_v2、export_dry_run_v3属于离线候选或纯预览，不能当作HTTP契约。

当前模块对象和 `origin/v4/integration@6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68` 均无api_*.md。真实整理preview/apply/revert及逐字段撤销端点仍缺，现WireChangeSet与模拟适配保留，不凭新类型名猜端点。

## 当前执行边界

运行源码61afdbe、前端测试与冻结构建没有变化，三轮稳定性仍2/3；完成第三轮后才正式迁入下一切片。不发真实模型、服务器或飞书请求，不新增依赖，不合并。P8当前ref为3a8f2f7fa98ec12d71f6827674452c2d0cf5637a，课程新版仍需独立整包来源核验，不混入现有七资产。
