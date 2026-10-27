# P10/P5b接口契约草稿回执

- 范围：mod.md v14；仅文档与Schema测试，不是P10产品或HTTP验收。
- 分支：v4/mod-api-contracts；Draft PR29，目标first-release，不合并。
- 基点：大脑指定e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd。PR相对目标含基点历史差异，采用时只认本线新增api文档/Schema测试提交，不把历史运行改动归于本线。

## 完成

1. 公共契约：认证owner、来源半开区间、稳定request_id、expected_revision、程序回执、安全错误、409保留草稿与unknown同ID对账。
2. 区/话题：列表、创建、改名/隐藏、移动/归档/事项关联、主副区消息路由。保留case并显式关联，保留原消息。
3. 整理：建议与具体话题预览、改名/合并/按消息拆分/移动/忽略、服务端24小时审阅凭证、精确计划应用、change_id字段精确撤销与后续编辑冲突。旧Q5仍record_only，不开放真实历史自动应用。
4. 画像：按区查看、来源/待确认、确认式单字段编辑、出生精度、敏感分类同意、两种删除范围与变更撤销；P8第七节只读，旧self/profile/confirm兼容待主线。
5. 研习：有版本引用的术语/课程与个人进度分离，进度初建修订0；课程不成为用户事实，completed不代表知识正确。

## 验证

离线运行 `private/mod-api-tests/run-offline.ps1 -TestArgs @('-m','pytest','tests/v4/api_drafts','-q','-p','no:cacheprovider')`：275 passed in 0.54s。Ruff lint/format通过。覆盖四组请求/响应合成正例、所有写操作缺ID/修订/越权字段/无效修订反例、精度/审阅/拆分/撤销回执等；所有Schema仅本地Registry解析。真实模型/飞书/服务器请求0，无PG或迁移。

## 未验证 / 需要主线配合

契约尚未冻结或接线；HTTP路由、事务授权与修订、幂等账本、原话真实性、审阅时效与原子消费、来源撤销、PG、前端及CI均未验证。Schema不能验证原话包含新值、跨对象引用、当前权限、时间顺序或并发执行。现有P5b move只认默认区，自建区需主线适配。采用前明确草稿路径对既有路由的兼容，保留用户草稿与既有回执协议；不据本回执宣布API可用。

## 迁移、回滚和后续

无运行代码与数据库迁移；回滚仅撤回本线文档/测试。四组JSON Schema2020-12嵌入对应api_*_draft.md，测试在tests/v4/api_drafts。主线采用后另做隔离PG/HTTP/前端验收；本模块线不继续扩大范围或开储备工作。
