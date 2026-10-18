# P10 增补阶段回执：功能区、话题与整理建议

- 分支 / 最后代码提交：`v4/p10-frontend @ e89a0e4a090dca74b90726c11d304766e21044d9`，基线 `241e874`；本回执随后仅补文档。
- 关联 PR：[草稿 #6](https://github.com/JerryandShawn/zhiming/pull/6)，本线未推送、未合并或强推。
- ExecPlan：[ExecPlan_spaces.md](../../../ExecPlan_spaces.md)；设计依据：P5b 增补 C、22 号 §6，指纹见 [design-inputs.json](design-inputs.json)。

## 完成了什么

- [x] 桌面“区 → 话题 → 对话”三栏；左栏七区与全部视图，每区最近活跃和未读数（包括零）。全部视图按时间显示 18 条合成消息。
- [x] 手机七区横滑标签与话题下拉；当前区 accent，其余 neutral；身心、财务用锁图标和文字表达敏感性。
- [x] 回答下方归区标签可改主区、话题或明确新建话题；输入框上方可改“将归入”。原消息 id、正文、角色和时间不改；移走回答后焦点回到对话标题。
- [x] “关于我”按七区列记忆、重要的人和事项；事项链接进入对应区/话题。整理草稿未应用时不改变已展示归属。
- [x] 整理树含区/话题数、消息数、时间跨度、≤80 字摘要及低把握文字提示；可改区名/话题名、合并、选消息拆分、移动、忽略。
- [x] 编辑先留草稿，应用和撤销均二次确认，取消不改变数据；应用产生演示 batch，撤销逐字段恢复；重复应用与会覆盖后续归区修改的撤销被阻止。忽略保留原消息与归属，不执行删除。
- [x] 明确 `?spaces=demo` 隔离模拟，刷新重置，发送/模型起名禁用；未读取真实对话、未接真实整理 API。默认 v3 数据模式继续保留。
- [x] 24 张四尺寸双主题矩阵 + 4 张交互截图，全部纳入本证据目录并提交；源码、构建、PNG SHA256 核对通过。

## 评测分数

| 检查 | 实际结果 |
| --- | --- |
| `npm run typecheck`、`npm run lint`、`npm run build` | 通过。 |
| `npm test` | **130/130**，16 个文件；较 M4 新增 41 项（状态 24、对话 7、整理 8、分区记忆 2）。 |
| `npx playwright test -c playwright.spaces.config.ts` | **6/6**，4.3 秒；覆盖桌面/手机、归区与新话题、刷新重置、五类编辑、应用撤销确认、焦点和真实/模拟入口隔离。 |
| `npx playwright test -c playwright.spaces-visual.config.ts` | **24/24**，31.3 秒；批次 `2026-10-18T09:09:34.711Z`。API/外域请求、console/pageerror、整页溢出、小字与 Axe AA 违规均 **0**。 |
| `npm run test:e2e` | **80/80** 既有静态回归，App/Layout 改动后复测；最后 favicon 和作用域颜色修正由最终 24 组矩阵覆盖。 |
| 原 M4 契约（独立开发服务 4174） | **12/12**，20.1 秒；真实 `core_test_fe` / 55481，脚本后端 8002；不把原取消 422 等已知阻塞改成成功。 |
| 旧前端 | 四套 CJS 与 `static/app.js` 语法检查通过。 |
| 首屏包体 | **83,564 / 204,800 bytes gzip**；[bundle-budget.json](bundle-budget.json)。未测 LCP。 |
| 全局脚本/真实模型/远程 CI | 本轮未跑全局语义评测或远程 CI；真实模型调用 **0**。 |

机器摘要：[checks.json](checks.json)、[visual-summary.json](visual-summary.json)；人工自评：[visual-review.md](visual-review.md)。模拟界面完全不需要后端；只有上述原 M4 回归使用隔离 PG 与脚本模型，不能把二者的验证范围混写。

## 截图索引

| 视口 / 主题 | 区与话题 | 分区记忆 | 整理建议 |
| --- | --- | --- | --- |
| 375 宣纸 | [图](screenshots/chat-light-375.png) | [图](screenshots/me-light-375.png) | [图](screenshots/organize-light-375.png) |
| 375 夜墨 | [图](screenshots/chat-dark-375.png) | [图](screenshots/me-dark-375.png) | [图](screenshots/organize-dark-375.png) |
| 390 宣纸 | [图](screenshots/chat-light-390.png) | [图](screenshots/me-light-390.png) | [图](screenshots/organize-light-390.png) |
| 390 夜墨 | [图](screenshots/chat-dark-390.png) | [图](screenshots/me-dark-390.png) | [图](screenshots/organize-dark-390.png) |
| 768 宣纸 | [图](screenshots/chat-light-768.png) | [图](screenshots/me-light-768.png) | [图](screenshots/organize-light-768.png) |
| 768 夜墨 | [图](screenshots/chat-dark-768.png) | [图](screenshots/me-dark-768.png) | [图](screenshots/organize-dark-768.png) |
| 1440 宣纸 | [图](screenshots/chat-light-1440.png) | [图](screenshots/me-light-1440.png) | [图](screenshots/organize-light-1440.png) |
| 1440 夜墨 | [图](screenshots/chat-dark-1440.png) | [图](screenshots/me-dark-1440.png) | [图](screenshots/organize-dark-1440.png) |

交互：[改区/新话题](interactions/route-new-topic-390.png)、[拆分选消息](interactions/split-editor-390.png)、[应用二次确认](interactions/apply-confirm-1440.png)、[撤销二次确认](interactions/revert-confirm-1440.png)。所有截图均为合成内容；未修改、遮盖或生成替代截图。

## 改了哪些关键文件

`web/src/spaces/**` 包含独立类型、合成样例、状态/整理操作及三页组件；App/Layout 提供模拟路由和侧栏，真实 Me 只新增预览入口。新增 Playwright 配置和测试；Vitest 收集 `.test.ts`，避免遗漏纯状态测试。新增本地 favicon 消除浏览器 404，包体脚本增加可选独立输出路径，未覆盖 M4 证据。

## 数据库迁移与回滚方式

无业务迁移或真实数据写入。模拟仅内存操作，刷新/重置即可复原。代码回滚使用 `git revert e89a0e4` 并重新构建，文档提交无需业务回滚。原 M4 复测只使用本线已存在的可丢弃库；17:15 +08 已关闭本线 8002/4173/55481 测试服务，证据与合成库文件保留，未动共享服务。

## 偏离设计的地方（及理由）

API 未落地前按用户要求采用独立合成预览，不为真实消息猜测区或伪造保存回执。当前未自动分类、未生成标题；这些由模块线/主线接入。夜墨 accent 改用已有 `--cinnabar-hover`，仅作用于本模拟以满足 AA，不改变全局 token。按 14§I6 既定口径排除品牌印章/导航指示后，内容朱砂强调各页均 ≤3。

## 未验证 / 已知风险

未验证真实 spaces/topics API、持久批次、owner/revision 并发、服务端 route_changed、自动路由/分类准确率、真实历史迁移、跨设备、飞书、4G LCP 或远程 CI。预览草稿刷新即丢失，页面已说明；不可用于整理真实聊天。原 P10/M4 未完成的取消、cookie/无痕等后端依赖仍在此前回执中，不因本增补而消失。

## 需要用户或大脑决定的问题

本轮没有需要等待用户的决定。需要主线提供最终实体与带 owner/request_id/expected_revision 的 API、route_changed 小版本协议、可撤销批次回执，再替换模拟适配层；需要主线在文件归属范围同步 22 号及 P5b 文档。真实旧对话在 stage/正式执行仍必须单独授权，本线没有执行。远端等价交接树的历史分叉保持原状，主线可按顺序接入 M4 和本增补提交后统一 CI；本线不强推或合并。

## 建议后续

大脑先审阅本目录截图与交互；API 到位后，用当前界面接真实适配层并增加幂等、409、撤销冲突、owner 隔离和 route_changed 的真实 PG 测试，再按授权执行真实整理。
