# P10 复核修正阶段回执

- 分支：`v4/p10-frontend`；PR：[草稿 #6](https://github.com/JerryandShawn/zhiming/pull/6)。发布记录将在验证后绑定代码提交。
- ExecPlan：[ExecPlan_spaces.md](../../../ExecPlan_spaces.md)；原 M4 与功能区回执保留，本页只记录大脑预览通过后的两项修正。

## 完成了什么

- [x] 桌面左栏使用 `position: sticky; top: 0; height: 100vh`，独立纵向滚动；外层整列背景延伸到长页底部。1440×900 的浅色、深色长页均验证滚到底后 top=0、height=900，底部仍落在左栏背景内。
- [x] 手机与平板宽度低于 1024 时，每个话题显示“改名 / 移动 / 更多”；更多菜单包含合并、拆分、忽略本批。桌面保留原五项直接操作。
- [x] 菜单支持方向键、Home/End、Esc；选择菜单动作后关闭再打开编辑器，取消返回更多。点击外部或 Tab 离开时保留新焦点；应用后入口全禁用。
- [x] 保留五类编辑、原消息不变、草稿、应用/撤销二次确认的既有测试。增加两主题的手机菜单与桌面滚动回归，重截矩阵和相关交互截图。

## 评测分数

| 检查 | 本轮结果 |
| --- | --- |
| `npm run typecheck` / `npm run lint` / `npm run build` | 通过 |
| `npm test` | 139/139，17 文件；本轮新增 9 项手机回归 |
| `npx playwright test -c playwright.spaces.config.ts` | 10/10，7.4 秒；原 6 项行为保留，增加两主题的两项修正回归 |
| `npx playwright test -c playwright.spaces-visual.config.ts` | 24/24，33.1 秒；四尺寸、双主题、三页面 |
| `npm run test:e2e` | 80/80 原静态页面回归 |
| 首屏 JS gzip | 83,566 / 204,800 bytes；未测 LCP |

最终命令结果和文件指纹见 [checks.json](checks.json)、[visual-summary.json](visual-summary.json)；真实模型调用为 0。本次只改展示与菜单，未重跑旧 PG 集成；原 12/12 的运行时间、范围及取消接口 422 限制仍见原 M4 回执，不作为本次新结果。

全局 Core/v4 语义评测、真实模型、飞书、4G LCP 本轮均未运行。远程 CI 状态在发布记录中单独列出。

## 相关截图

| 修正 | 宣纸 | 夜墨 |
| --- | --- | --- |
| 桌面滚动到底部 | [图](interactions/desktop-sidebar-scrolled-1440.png) | [图](interactions/desktop-sidebar-scrolled-dark-1440.png) |
| 手机更多菜单 | [图](interactions/mobile-more-390.png) | [图](interactions/mobile-more-dark-390.png) |
| 桌面完整长页 | [图](screenshots/organize-light-1440.png) | [图](screenshots/organize-dark-1440.png) |
| 手机完整长页 | [图](screenshots/organize-light-375.png) | [图](screenshots/organize-dark-375.png) |

截图来自本机实际浏览器的合成预览，无真实资料；未为截图隐藏导航或改变定位。矩阵 24 张与交互 8 张合计 32 张。

## 改了哪些关键文件

- `web/src/Layout.tsx`、`web/src/styles/base.css`：完整背景列与 sticky 内栏。
- `web/src/spaces/TopicActions.tsx`、`ProposalTree.tsx`、`organize.css`：响应式操作入口和菜单。
- `web/tests/spaces-organize-actions.test.tsx`、`spaces-organize.test.tsx`、`tests/e2e/spaces.spec.ts`：手机操作、焦点、桌面滚动回归；视觉摘要新增 base.css 和行为测试指纹。

## 数据库迁移与回滚方式

无迁移、无后端或真实资料写入。模拟刷新即恢复；回退本轮修正代码提交并重新构建即可。只启动本机 4173 构建预览，未启动 8002 或测试 PG，也未接触 stage/生产。

## 偏离设计的地方

无。本次按大脑的两项复核意见修正；独立合成预览仍是用户明确要求的 API 落地前方案。

## 未验证 / 已知风险

真实功能区 API、持久化批次、owner/revision 并发、route_changed、自动分类和真实历史整理仍未接通。此前 M4 的取消接口、cookie/无痕及其它后端依赖没有因界面修正而解决；整个 P10 仍不能宣称 Done。

## 需要用户或大脑决定的问题

本轮无新增待决问题。用户已明确授权推送同名远端与更新 PR #6；保持草稿，不执行合并。

## 建议后续

主线提供真实 API 和冻结的 SSE v2 协议后继续联调，并修复已记录的取消 422；按既有边界独立安排 stage、飞书真机及完整 P10 验收。
