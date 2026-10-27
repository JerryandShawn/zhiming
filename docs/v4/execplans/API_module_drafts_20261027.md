# P10/P5b接口契约草稿（v14）

## Purpose

只新增docs/v4/contracts/api_*.md和Schema测试，给主线采用，不注册路由、不改服务/Agent/闸门。工作树zhiming-v4-mod-api-contracts，分支v4/mod-api-contracts，从板指定e578e2d建立；P9纯模块已交付f38406c/PR27。四组：区话题、整理建议/审阅/撤销、画像查看编辑、研习区。全部完成写接口契约草稿就绪后结束续作。

## Progress

- [x] (2026-10-27T16:49:17.263397+08:00) 已读05/P10完整、P5b回执与review_gate；查首发现有api_runtime_v1与旧profile路由，只读不改。
- [x] 公共Schema：身份/修订/来源/回执/错误，owner只来自认证，未知字段拒绝，全部写request_id+expected_revision。
- [x] 区与话题：列表/创建/改名隐藏/话题移动归档/消息路由，兼容case关系；只起草不宣称已实现。
- [x] 整理：建议→编辑→当前计划审阅凭证→应用→字段精确撤销；旧Q5门保留，禁止直接自动应用历史。
- [x] 画像：查看条目/按区显示、来源、确认式编辑、敏感/出生资料提案与显式确认；不直接覆盖旧self/profile/confirm。
- [x] 研习：术语/课程/进度Schema、只读内容与个人进度分开，不让课程文字成为用户事实。
- [x] 正反例与Schema一致性、端点映射、错误/幂等/revision测试，一页回执与Draft PR，写就绪结束任务。

## Surprises & Discoveries

当前api_runtime_v1明确画像/分区仍待契约；旧POST /api/subjects/self/profile/confirm已存在，但其字段与新确认式编辑必须由主线做兼容适配，不能文档当成运行实现。P5b旧Q5质量门未解除。

## Decision Log

使用JSON Schema2020-12嵌入Markdown的json代码块，测试提取并本地解析，不另造运行Schema模块或路由。现有api_runtime_v1/线程事件/core4信封保持不变。所有端点明确draft状态；身份从服务端解析，路径subject须授权，客户端不得传owner/runtime/provider/lane。对前端409保留草稿、模糊结果同ID重试/对账、来源撤销与一次性审阅约束逐条写清。

## Outcomes & Retrospective

接口契约草稿就绪 daccd26cd68f6b790f778946a9c3a769408216b2；四组专题、公共约束及275项本地Schema检查完成。无运行API、PG、UI、CI或真实请求验证，主线采用边界见api_modules_handoff.md。

2026-10-27T16:50:23.906654+08:00 公共Schema首段23项定向通过（0.25s），覆盖创建0/修改修订、未知owner/runtime拒绝、程序回执显式状态与安全错误；四组专题仍未完成，不写接口契约草稿就绪。仅文档与Schema测试，无运行API变更。

2026-10-27T17:21:26.102933+08:00 四组专题契约与本地Schema正反例完成；275项通过0.54s，Ruff lint/format通过。case保留双向引用意图，split按消息子集且title<=80，自建区move须主线适配；仅契约草稿验收，不含HTTP/PG/产品接线。待记录测试候选SHA并暂停自动续作。

2026-10-27T17:22:20.441966+08:00 测试候选daccd26cd68f6b790f778946a9c3a769408216b2已推送；ready记录只追加文档，不改已测Schema/测试。按v14全部完成后暂停续作。
