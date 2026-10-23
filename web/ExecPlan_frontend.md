# P10：接入 v3 页面与对话，并验证 SSE v2 客户端

遵循 AGENTS.md 与 .agent/PLANS.md。本计划放在 web/，遵守用户此次仅修改前端、前端测试及指定日报的边界。

## Context and Orientation

目录 C:/Users/Administrator/Documents/Codex/zhiming-v4-p10，分支 v4/p10-frontend。2026-10-18 15:50 +08 确认工作区干净；交接头 f65d3ba，父提交 ea4cb5a 已完成 14§I 六项，不重做。复用 adapters/web.py 的现有 API、adapters/tarot.py 的公开 viewer、application/consultation.py 的程序结果以及 web/src/components 的 token 组件；不修改后端文件。服务端抽牌、owner 隔离、来源授权、固定牌与回执、幂等和 revision 契约不变。

## Purpose / Big Picture

默认七页接真实 v3 API，保留显式静态预览用于既有 M1/M2 视觉回归。测试用 core_test_fe 与 127.0.0.1:8002，替换模型提供方，仍走真实 PG 与业务服务。旧格式 SSE 先接入；SSE v2 仅验证本地模拟事件，等待 P4 冻结协议再联调。

## Progress

- [x] (2026-10-18 15:40 +08) 首次检查见未提交 §I，等待期间不写文件。
- [x] (2026-10-18 15:50 +08) 10 分钟复查确认干净及 §I 提交，开始 M4。
- [x] 完整阅读 20、P10、08、08b；核对 AGENTS、PLANS、蓝图 §9/14/16 与评测场景。
- [x] (2026-10-18 16:25 +08) 接入鉴权、稳定写操作、七页 v3 接口；没有后端的新版功能禁用并记下依赖。
- [x] (2026-10-18 16:39 +08) v3 对话、同轮恢复/重试、历史及 v2 模拟客户端；取消真实返回 422，未冒充成功。
- [x] (2026-10-18 16:39 +08) 真实隔离 PG + 脚本模型的 12 项 Playwright 通过，覆盖 11 条契约及 v2 模拟；后端阻塞见逐条回执。
- [x] (2026-10-18 16:47 +08) 最终只读复核发现历史恢复会覆盖未确认一轮；修复后全量 89 单测、typecheck/lint/build 通过。
- [x] (2026-10-18 16:48 +08) 共享 PG 退出，未重启主线数据目录；在 web/test-results/ 新起专用 PG 15.19，core_test_fe / 55481，后端仍为 8002。
- [x] (2026-10-18 16:53 +08) 最终 56 真实页面矩阵、12 契约复测、80 静态浏览器回归、旧前端四套与语法检查通过；证据摘要与逐页自评已写。
- [x] (2026-10-18 16:55 +08) 代码本地提交 63800ca，§11 日报回执绑定代码验收头；后续仅提交回执。保持草稿 PR，不推送/合并或强推。

## Surprises & Discoveries

现有 API 仅 X-Token 鉴权；cookie 会话、无痕语义、独立 proposal API、SSE v2 events 与 run-events.schema.json 尚不存在。相关能力禁用或明确模拟验证，记入日报，由主线补接。v3 历史是正序数组，分页游标必须取服务端 cursor；资料 effective 是扁平键。塔罗牌背只能使用服务器 opaque back_id。

真实取消请求返回 422：adapters/web.py 的 stop(ident, req) 缺少 Request 注解，FastAPI 要求 query.req。前端保留运行状态，不添加假 query 绕过。塔罗旧写接口不检查 expected_revision。命盘真实五行 SVG 未指定宽度时按 viewBox 推成 800px；为该真实图表明确设置 100% 宽，并约束窄屏 grid 列。

结构化资料确认会在旧历史生成包含出生原值的 web-action 记录；新增公开文本投影将这类记录和 birth.* 依据隐藏，资料页之外不泛化展示原始 JSON。普通日期与事项文本保留。字体与现有设计系统沿用交接头，不重做 §I。

## Decision Log

2026-10-18 / 前端线：用户此次指令优先，忽略旧主线工作；不触碰 zhiming-v4、zhiming-v4-p8，不合并 PR，不发真实模型或飞书请求。所有新增实现放 web/；日报是用户明确授权的文档例外。

2026-10-18 / 前端线：静态页面保留在显式 preview=1 模式，旧静态测试改为明确选择预览，原静态行为断言保留。默认页面走真实 API；不能为了保持旧零 API 断言而伪造接入。409 草稿不清空，确认冲突后禁写；模糊失败保留同 ID 和参数。

2026-10-18 16:25 +08 / 前端线：报告成功回执还必须与本次提交的 enabled/time/weekday/day 匹配。新增反例测试拒绝其他政策的有效版本回执。原 409 单测的模拟成功响应错误返回服务器旧时间 11:00，但原断言保护用户草稿 07:00；修正该夹具为已提交的 07:00，保留全部 409、草稿、revision 和载荷断言，没有放宽行为契约。

2026-10-18 16:47 +08 / 前端线：公共写操作在会话存储不可用时拒绝发送，不以仅内存回退冒充跨刷新重试。历史恢复从当前 owner 的持久 pending 检查：不同运行不能覆盖尚未确认的 ID/附件，同轮恢复复用完整原载荷；两条新增测试覆盖断线、历史切换、卸载/刷新与附件不丢失。

2026-10-18 16:48 +08 / 前端线：旧服务和共享 PG 55480 在复测期间退出。为了不更改 zhiming-v4 的数据目录，使用本工作树已忽略的 web/test-results/pg-fe-20261018 初始化单独 PG 15.19 / 55481。夹具可用 FRONTEND_TEST_DSN 选择该实例，仍只接受 loopback、core_test_fe 与 55480/55481。前端契约可在 4174 开发服务运行，让 4173 始终检查构建；业务后端仅 8002。

2026-10-18 / 前端线：清理生成截图目录被自动审批阻止，改为保留所有旧批次，新增 run_id 目录并按批次汇总；没有改用其他方式删除，也没有改写初次失败证据。

## Plan of Work

先实现公共鉴权、JSON 请求与 sessionStorage 中的稳定操作编号，再并行接入数据页、塔罗和对话。创建只在本地测试运行的 FastAPI fixture，硬性限定 core_test_fe 和 localhost，模型为脚本提供方，禁止外部 HTTP。通过真实端到端与断线/冲突注入验证行为；v2 通过模拟事件服务验证传输与渲染，明确不是后端完成。

## Concrete Steps

在 web/ 使用 Node 22：

    npm run typecheck
    npm run lint
    npm test
    npm run build
    npm run test:e2e

仓库根目录，已配置独立 Charts 解释器和本机测试 PG：

    python -m web.tests.fixture_server

web/ 目录的额外检查：

    npx playwright test -c playwright.contracts.config.ts
    npx playwright test -c playwright.live-visual.config.ts
    node scripts/bundle-budget.mjs

## Validation and Acceptance

按 P10 的 11 条行为契约逐项记录实际证据，覆盖 request_id、409、运行生命周期、资料确认、记忆回执、塔罗固定、报告载荷、深链、可访问性、401 与私有字段。相关评测 ID：M03/M05/M12、F01/F03、C02/C06、TA01/TA02、X04/X08。这里只验证前端和程序行为，不宣称真实模型评测通过。

## Idempotence and Recovery

所有写操作在有效回执前保留请求编号及原参数；网络错误可用相同意图重放。已知 409 后用户读取最新版本并明确核对才解锁。测试只使用隔离库，服务端代码与迁移不变；回退本线提交即可恢复前端。

## Artifacts and Notes

新测试报告保存在 web/test-results/frontend/、contracts/、static-evidence/ 与按批次分开的 live-evidence/；可提交的摘要和构建哈希在 web/evidence/2026-10-18/。日报 docs/v4/daily/2026-10-18_frontend.md。旧 docs/v4/evidence/P10/ 截图与参考保持原提交内容。

## Interfaces and Dependencies

复用已有依赖，不添加运行时外网资源。开发预览同源代理 API 到 8002；真实入口切换与 cookie/无痕/v2 后端由主线处理。

## Outcomes & Retrospective

本线落地现有 v3 API 和客户端恢复行为，不宣称整个 P10 Done。v2 仅本地模拟，取消、cookie、无痕及新版 proposal/主动设置仍需后端。紫微/星盘为真实字段列表，完整动态图形、4G LCP、飞书真机与生产入口切换未验证。完整 Core/v4/评测与远程 CI 不在本次前端验证范围，真实模型调用 0。

最终本地结果：89/89 单测、12/12 隔离 PG 契约、80/80 原静态浏览器检查、56/56 真实数据页面矩阵通过；矩阵的溢出/AA/小字/外网/JS 错误全为 0。默认入口加 Today 路由 JS gzip 83,015 bytes，预算 204,800 bytes；不代表 LCP 达标。人工复核部分最终截图，详细差异保留在 visual-self-review.md。

发布边界：远端 PR #6 仍为草稿。GitHub 头 8b65459 和本机交接头 f65d3ba 树相同，但远端头不是本机祖先；不强推、不重写交接历史。本线交付本地代码提交，主线可在远端等价交接树上 cherry-pick 后再统一运行 CI 和更新 PR。

2026-10-18 16:55 +08：核对 76 份前端源码哈希、全部构建 JS/CSS 哈希、56 张最终 PNG 与 56 份审计均匹配。仅关闭本线 8002/4173/55481 测试服务，保留生成数据；没有触碰共享服务。

## 修订记录

2026-10-18 15:50 +08：确认交接门后创建前端线计划，记录范围与真实接口缺口。
