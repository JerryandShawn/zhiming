# P10 阶段回执：命盘、塔罗、月历与 M5 本机打磨

- 分支 / 最后代码提交：`v4/p10-frontend @ 96160ca`；PR：[草稿 #6](https://github.com/JerryandShawn/zhiming/pull/6)，base=`v4/main`，仅普通推送，不合并。
- ExecPlan：[四项执行计划](../../../ExecPlan_components_M5.md)；[逐项日报](../../../../docs/v4/daily/2026-10-18_frontend.md)。本次是已接 v3 的 M4 组件补齐与 M5 本机验收，不代表整个 P10 Done。
- 代码范围：`web/**`；用户明确例外只追加前端日报。未修改命理线或主线工作树，未改后端/数据库迁移/运行配置，未访问 stage/生产。

## 完成了什么（对照本次四项）

- [x] 命盘：紫微桌面 4×4 周边十二宫、中央信息；手机默认列表并可切内部横滚网格。星盘 SVG 投影已返回的星体/宫头/相位，不补造缺失相位；大运可点解释，并按 P8 精确半开交运边界判断。时辰口径默认真太阳时，同一时刻的北京时间结果不同时并列展示，不自行换算出生时辰。
- [x] 塔罗：单张、三张横排、五张十字；78 张不透明牌背六/十三列键盘导航，锁定位置不压缩；回执后逐张翻牌 600ms、全部揭开间隔 90ms；减少动效直接呈现。原固定牌、稳定请求、失败解读不换牌、A/B 冻结与隐私投影保持。
- [x] 今日月历：休/班/节气/节日/你的安排，五类均有文字或可访问名称与图例；节气和安排双点可共存，今天与选中日期区分。桌面内联，手机 Sheet。来源明确区分覆盖、未知和显式未公布，不按年份猜调休，不从事项反馈制造未来安排。
- [x] M5 本机：浅深主题 Axe、safe-area、横屏、键盘视口高度/偏移/缩放/失焦、Panel 返回先关闭与回焦、文本草稿往返保留；Feishu UA 仅调整外观并保留设置入口。正式 Today 冷缓存模拟 4G 的五次 LCP 全部低于 2.5 秒。
- [x] 每项均先测试、截图、追加一行日报，再进入下一项；提交依次为 `b4c7c13`、`4bb772d`、`7fcfb8c`、`96160ca`。
- [ ] 飞书 SDK、免登、真机与原生返回桥验收：未提供本次环境或 stage 授权，未执行，不能以浏览器仿真代替。

## 评测分数

| 最终检查 | 结果与口径 |
| --- | --- |
| typecheck / lint / build | 通过 |
| Vitest | 231/231，24 文件；本次新增 92 项 |
| 原静态页面 / 功能区 / 新组件行为 | 80/80 + 10/10 + 10/10 |
| 375 / 390 / 768 / 1440 × 浅深主题 × 八状态 | 64/64；Axe AA、溢出、小字、API/外域请求、console/pageerror 均为 0 |
| 嵌入外观/安全区/键盘/历史仿真 | 8/8；6 份 Axe 报告无违规，8 份安全报告，真实模型 0 |
| 真实隔离 PostgreSQL 契约 | 12/12；`core_test_fe:55481`、后端 8002、业务服务真实执行，模型仅脚本替身 |
| 本机浏览器检查总计 | 184/184（包含以上矩阵及 PG 契约，不把重复阶段运行再次相加） |
| 初始 JS gzip | 84,059 / 204,800 bytes，包含提前加载的正式 Today |
| 4G LCP 五次 | 2456 / 2452 / 2444 / 2452 / 2432 ms；p75=2452 ms |

测量：Chrome 155.0.8059.82，390×844、DPR 2、移动/触摸、下载 1.6Mbps、上传 750kbps、150ms 延迟、CPU 4×，每轮新 context，禁用并清空 HTTP 缓存，阻止 Service Worker，普通动效。预置合成登录和经确认的合成排盘资料，加载正式 Today 与真实隔离 PG 接口；等待页面数据/字体稳定后读取 buffered LCP，未点击、未测登录框或骨架。LCP 候选为流日方法说明段。

基线 p75=5912ms。资源瀑布显示字体与数据竞争；提前发现默认 Today、给前台 Fetch 高优先级后达标。完整字体、内容与接口保留，没有延后内容或裁剪字体来改变指标。该成绩限本机这组参数，不等于生产或飞书真机成绩。

v4 后端评测 runner 本轮未重跑，不用前端契约分数替代其分数。真实模型实测未运行，遵守用户“零真实模型”约束。远程 CI 状态以推送后 PR 的最新检查为准，不能用此前 `c9ebacb` 的绿色状态替代本轮。

## 验收证据与截图

- [总检查](checks.json) · [最终 64 组合及 source/build/PNG 哈希](all-visual-summary.json) · [初始 JS 预算](initial-js-budget.json)
- [最终 4G 原始资源与五轮报告](performance/final/report.json) · [原始基线](performance/baseline/report.json) · [最终首屏截图](performance/final/run-1.png)
- [嵌入仿真与截图哈希](embed-checks.json) · [Axe/安全报告](embed-audits)
- 阶段历史：[命盘](chart-checks.json)、[塔罗](tarot-checks.json)、[月历](calendar-checks.json)。各自哈希属于当时提交；最终源码/构建以 `all-visual-summary.json` 与 `performance/final/report.json` 为准。

最终构建共 93 张截图：64 张矩阵、24 张交互、5 张性能；另外保留 13 张基线/中间性能截图，未删除失败前后的测量历史。已人工查看桌面紫微、手机星盘、三牌阵/牌背、月历 Sheet、横屏安全区、offset=120 键盘与飞书深色仿真等关键画面；source/build/font/PNG 指纹已复核。

| 画面 | 证据 |
| --- | --- |
| 桌面紫微十二宫 | [宣纸 1440](screenshots/ziwei-light-1440.png) |
| 手机星盘与相位 | [夜墨 390](screenshots/astro-dark-390.png) |
| 五张十字牌阵 | [宣纸 390](screenshots/tarot-choice5-light-390.png) |
| 78 张牌背 | [夜墨 1440](screenshots/tarot-picker-dark-1440.png) |
| 五类月历标记 | [宣纸 1440](screenshots/today-light-1440.png) |
| 手机月历 Sheet | [宣纸 390](screenshots/today-light-390.png) |
| 横屏安全区 | [844×390](interactions/embed-browser-landscape-safe-area-844.png) |
| 键盘偏移仿真 | [height420 / offset120](interactions/embed-keyboard-height420-offset120.png) |
| Feishu UA 仿真 | [夜墨键盘](interactions/embed-feishu-dark-keyboard420.png)、[月历](interactions/embed-feishu-dark-calendar-panel.png) |

08 §10 自评：

- [x] 页面保留一件主事，没有新增装饰性大标题；分组使用留白和细线。
- [x] 字号、颜色使用 token；普通文字 ≥13px，导航/日历微标/引用标记仅用规范允许的例外。
- [x] 原朱砂每屏 ≤3 重点断言保留并通过；新增安排点使用 ink-2，节气使用 gold，今天使用朱砂框。
- [x] 图形使用 SVG/lucide/文字标签，无 emoji 装饰；浅深主题可读。
- [x] 375/390 整页无横溢，紫微横滚仅限网格容器。
- [x] 焦点、Esc 回焦、减动效与回执/失败重试契约保留；原静态页面回归和新组件矩阵均通过。
- [x] 本次以 08 的具体规格与旧参考稿已建立的框架对照；新增真实字段图形和双时辰说明由本次需求补充，不将合成预览称为真实排盘接通。

## 改了哪些关键文件

`web/src/charts/**`、`live/Chart.tsx` / `ChartData.tsx`；`components/TarotCards.tsx`、`tarot/CardBackGrid.tsx` / `FlipFace.tsx` / `ServerSpread.tsx`；`calendar/**`、两个 Today 页面；`Layout.tsx`、`useKeyboardViewport.ts`、`usePanelHistory.ts`、`useViewportPortalStyles.ts`、`api/client.ts`、相关 token 样式。组件文件均 ≤250 行，无新增运行时依赖、CDN 或真实模型路径。

`web/scripts/measure-mobile-lcp.mjs` 可复现性能；`npm run test:e2e` 现在包括原页面、功能区、新组件和全矩阵，便于现有 CI 覆盖。`test:embed`、`test:perf` 与 PG 契约需要先启动明确隔离的本机 fixture，未悄悄加入无后端的 CI。

## 数据库迁移与回滚方式

无迁移，无真实数据写入。合成演示入口为 `?components=demo#/chart` / `#/tarot?spread=choice5&step=reveal` / `#/today`，仅在本地改变示例状态；默认入口继续使用 v3。

按需要逆序 revert `96160ca`、`7fcfb8c`、`4bb772d`、`b4c7c13` 后，在 `web/` 重建。测试服务仅使用本线创建的 PG 数据目录/55481 与脚本后端 8002；不操作其他工作树的数据库或生产服务。

## 偏离设计的地方（及理由）

用户指定仅改 web，因此计划、证据与回执放在 `web/`，只对指定日报做文档例外。缺真实 time_basis/日历源时，正式页标缺口，用明确的合成入口验收组件。08 未规定安排点颜色，为符合既有朱砂预算使用墨色；未改旧测试来接纳超标。旧塔罗单测只有一处按钮定位兼容普通/减少动效两种准确标签，固定牌/回执/失败恢复断言均保留。

## 未验证 / 未完成 / 已知风险

1. v3 未提供完整 P8 `time_basis` envelope；正式页不能凭旧字段宣称已切到真太阳时，双口径须等真实 API 接入。没有修改或导入命理线实现。
2. v3 暂无官方假期、节气、节日和用户安排的月历源；正式页显示未知，不展示样例面试或假期。排盘语义准确性与生活预测不属于本轮浏览器验证。
3. 飞书 SDK、P9 cookie 免登、真机内核/键盘、原生返回桥与 stage 均未验证；UA/CDP/VV 测试只证明这组浏览器仿真。
4. 返回处理覆盖共用 Panel；直接 Radix 编辑/选择弹层尚未统一接入这套历史管理。跨路由已关闭 Panel 的物理历史哨兵可能仍存在，前进不会重开。未发送附图跨路由暂不保留；文本草稿已有保留验证。
5. 既有取消接口 422、服务端 SSE v2/持久游标、真实功能区 API/整理持久化、无痕及其它主线依赖继续保留；本轮不冒充修复。

## 需要用户或大脑决定的问题（待决问题）

- 本轮没有新增产品决定需要等待。后续由主线提供 P8 口径与日历源、冻结 SSE v2/P9 接口后联调。
- 真机/原生返回桥和 stage 验证留待有环境及对应授权时执行；本次未请求夜间答复或擅自访问。

## 建议后续

先接真实 `time_basis` 与月历源，再在授权的飞书真机验证免登、键盘和原生返回；统一剩余直接 Radix 弹层历史与附图草稿。保持 PR #6 草稿，等待大脑复核与后续主线接口联调。
