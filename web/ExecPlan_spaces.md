# P10 增补：功能区、话题与整理建议的前端模拟

本计划遵循 AGENTS.md 与 .agent/PLANS.md，是前端线在 M4 交付后的增补；原 M4 的结论和未完成后端依赖保持有效。

## Context and Orientation

目录 C:/Users/Administrator/Documents/Codex/zhiming-v4-p10，分支 v4/p10-frontend，开工前工作区干净，基线 241e874。设计来自大脑交付目录 P5b 增补 C 和 22 号文件 §6，均已完整阅读。复用 Controls.tsx 的 Tag/Button/Input、Selection.tsx 的 Select、Overlays.tsx 的 Panel 和 Messages.tsx 的消息气泡，以及既有 Layout 和 hash 路由。不得改变真实 v3 的稳定 request_id、owner 隔离、409 草稿、固定塔罗和程序回执契约。

## Purpose / Big Picture

用明确的合成预览展示区到话题的导航、消息归区修改、按区分组的记忆，以及可编辑的整理建议。用户能查看七个区、切换话题或全部时间线、修改归区，并演示整理草稿的应用与撤销。API 尚不存在，因此所有这些变动仅在本页内存中，刷新重置，不触发真实聊天、模型、分类器、数据库、stage 或生产整理。

## Progress

- [x] (2026-10-18 16:56 +08) 检查干净分支，完整阅读 P5b 与 22；确认当前代码没有 spaces/topics/organize API。
- [x] (2026-10-18 17:06 +08) 合成资料与整理状态：改名、合并、拆分、移动、忽略；应用/撤销精确恢复原标签和消息，24 项状态测试。
- [x] (2026-10-18 17:06 +08) 桌面区/话题/对话三栏、手机区标签/话题下拉、回答与输入框归区控件。
- [x] (2026-10-18 17:06 +08) 关于我按区分组，整理建议树和二次确认。
- [x] (2026-10-18 17:13 +08) 130 项单测（新增 41）、6 项功能区 E2E、24 组视觉矩阵、原 80 项静态回归、12 项真实 PG 契约复测全部通过；类型/lint/build 及旧前端四套检查通过。
- [x] (2026-10-18 17:15 +08) 代码提交 e89a0e4；阶段回执与截图索引绑定该验收头，随后仅补文档。不推送/合并，已关闭本线测试服务。

## Surprises & Discoveries

当前分支没有 /api/spaces、/api/topics、/api/organize 或 route_changed；不能把真实历史按未经验证的规则贴标签。22 号设计尚未同步至本分支 docs/v4，本线只读大脑目录，不越过 web/** 与指定日报的文件归属边界去覆盖共享文档。

首批截图审计查出未声明 favicon 导致浏览器请求 favicon.ico 返回 404，以及旧 accent 夜墨配色在 13px 标签上仅约 3.69 对比度。新增自托管 favicon，并仅在功能区模拟中使用既有 cinnabar-hover token 加深可读性；没有降低 AA/零 console 的断言，也未修改全局调色板。

## Decision Log

2026-10-18 / 前端线：采用 ?spaces=demo 的明确模拟模式，默认 v3 不掺入合成消息或假回执。全部模拟资料放 web/src/spaces/fixtures.ts，独立 Zustand 内存状态，不使用真实 token，不读取真实历史，不做本地自动分类。页面和动作均说明本地演示；刷新回到初始状态。用户已明确授权 API 未落地前用模拟数据，不再询问默认七区或整理方式。

2026-10-18 / 前端线：仅编辑话题/区元数据与消息归属；原始消息 id、正文和时间不可变。忽略保留原归属，不能当作删除。应用生成演示 batch，撤销需确认并恢复快照；批次之后发生新标签更改时拒绝旧快照覆盖新修改。

2026-10-18 / 前端线：App 在模拟聊天切换区/话题时保留组件草稿，输入归属随新话题重新选择；刷新仍清空。归区后若当前回答移出列表，焦点回到对话标题。保留 M4 证据与包体报告，新预算脚本接受独立输出路径，避免覆盖历史验收快照。

## Outcomes & Retrospective

功能区模拟界面已按 C / §6 落地：七区与全部时间线、桌面三栏和手机切换、可改归属、分区记忆及五类整理编辑、应用/撤销二次确认均有组件和浏览器证据。130 项单测、6 项新增行为 E2E、24/24 矩阵通过；原 80 项静态与 12 项真实 PG 契约复测通过。24 张矩阵图和 4 张交互图可提交，全部源码/构建/PNG 哈希核对通过。矩阵 API、外域、console、页面错误、溢出、小字与 AA 违规均为 0。

默认入口加 Today 路由 gzip 83,564 bytes，预算 204,800 bytes；未测 LCP。仅原 M4 回归使用 core_test_fe / 55481 和 8002 脚本后端；功能区测试本身完全不需要后端、不发送 API 或模型请求。该原型不代表 P5b 的实体、分类器、API、真实历史回填、上下文分区或飞书已完成；这些仍待主线/模块线提供后再换适配层。

## Plan of Work

先约定共享类型与纯内存数据契约，再并行实现对话导航和整理建议 UI，主线前端整合 App/Layout 与关于我。保留现有组件与设计 token；编辑对话用 Radix，敏感区用锁形图标，当前区用 accent，其余 neutral。最后在构建预览上验证全部编辑路径、确认取消、应用撤销、键盘焦点、无 API/外域请求、跨刷新重置，并截图审计。

## Concrete Steps

在 web/，Node 22：

    npm run typecheck
    npm run lint
    npm test
    npm run build
    npx playwright test -c playwright.spaces.config.ts
    node scripts/bundle-budget.mjs evidence/2026-10-18/spaces/bundle-budget.json

浏览器入口：

    http://127.0.0.1:4173/?spaces=demo#/chat
    http://127.0.0.1:4173/?spaces=demo#/me
    http://127.0.0.1:4173/?spaces=demo#/organize

## Validation and Acceptance

可观察验收：桌面选择区后中间列话题、右边仅所选话题；全部按时间看各区。375/390/768 手机上标签可横滑、话题可键盘选择、输入框上方可改归属。回答标签改区/新话题后只改合成路由，不更改正文。关于我每区有记忆、重要的人与事项。整理树编辑只改草稿，取消应用/撤销均不改数据；确认应用后看到本地 batch，确认撤销恢复原状，忽略不删除消息。相关候选 SP01/SP04/SP06，只验证 UI/本地状态；不宣称本地分类或跨区上下文通过。沿用 07 中 M03/M05 与 X04/X08 的回执、修改和隐私边界，不触发全局评测。

## Idempotence and Recovery

演示重复应用不产生第二批，已应用后草稿锁定；撤销先核对演示版本，不覆盖后续归区更改。刷新或重置恢复合成初始状态。无迁移、无后端写入；回退本轮前端提交即可。截图按批次分目录，不删除 M4 的已有证据。

## Artifacts and Notes

新证据放 web/evidence/2026-10-18/spaces/（24 张矩阵图、4 张交互图、摘要、自评和哈希）；完整逐图审计放已忽略的 web/test-results/spaces-visual-evidence/，行为报告在 web/test-results/spaces-evidence/。每日回执追加 docs/v4/daily/2026-10-18_frontend.md，保留前一轮 M4 记录。

## Interfaces and Dependencies

使用现有 React/Zustand/Radix/Playwright，无新增运行时包或 CDN。模拟用独立 Dataset/Proposal/AppliedBatch 类型和同步动作；不猜测未来 API 响应结构。后续转正条件是主线提供实体、owner/revision/幂等 API、route_changed 协议及可撤销批次回执，再替换该模拟适配层。

## 修订记录

2026-10-18 16:59 +08：建立增补计划，明确模拟、文件归属、原文不变与确认/撤销边界。

2026-10-18 17:13 +08：补充实际测试、28 张截图、哈希与已发现/修复的可访问性问题，保留模拟与真实后端验收的边界。
