# 字体预加载候选：只读调查与验收边界

本笔记由前端子任务离线整理。仅写入 ignored `web/test-results/font-preload-plan/`，未修改正式源码、字体、样例或测试，未运行测试、构建、浏览器或 HTTP。所有时间说明均按北京时间。

## 结论与当前候选

08 §3 对首屏预加载有明确要求，不能全部移除后仍称完全遵循设计。当前供 root 独立性能切片验证的最小候选是：

1. 保留 `/fonts/noto-sans-sc-119-wght-normal.woff2` 常用 Sans 切片预加载，增加 `fetchpriority="low"`。
2. 移除 `/fonts/noto-sans-sc-latin-wght-normal.woff2` 的独立预加载；该字面文件仍由完整 CSS 按需请求，并仍在 PWA shell 四字体白名单中。
3. 保留字体 stylesheet、`font-display: swap`、全部 202 个 face、所有 WOFF2 字节、字体栈及 OFL。页面文字、业务内容和验收口径不变。

这是待测候选，**尚无收益测量**。Latin 的 24,880 B 是从早期预加载时段移出，不能称总字体字节减少；保留项的 `low` 是提示，不能保证浏览器必须让出某个时段的带宽。

## 设计依据核对

最新大脑交付文件与仓库文件的 §3 第 107 行一致：

> 自托管 + unicode-range 切片；首屏只预加载 `--font-sans` Regular 的常用字切片；`font-display: swap`。

来源：

- 大脑交付：`outputs/明镜台v4_大脑交付/08_设计规范_新中式.md:107`。
- 仓库：`docs/v4/08_设计规范_新中式.md:107`。
- 当前入口：`web/index.html:11–13`，完整字体 CSS 后有 CJK119 和 Latin 两条 Sans 预加载。

因此早先“删除两条预加载”的调查方向已收回。保留常用 Sans 切片的候选与该要求一致；仅保留 Latin 切片不足以替代中文常用字切片。样式源的 Variable 字体仍覆盖既有权重范围，不为本候选删字或改字重。

## 原始五冷基线：不合格报告保留

原始报告：`web/evidence/2026-10-21/tools-pagination-performance/final/head-e025f9f-1008/report.json`。

- 记录时间：`2026-10-21T10:08:29.158+08:00`（以 JSON 原始字符串为准；PowerShell 将日期对象重序列化可能显示本机 +09:00，不能据此改写北京时间记录）。
- HEAD：`e025f9fb3ba4cfde437bd48da3bc5725324a6a82`；报告确认测量期间源码与构建均保持不变。
- 路由：`/#/today`；已填充数据的真实 Today UI，本机合成 `core_test_fe` 数据，未登录弹窗数 0。
- 390 × 844、DPR 2、手机触控；RTT 150 ms、下载 200,000 B/s、上传 93,750 B/s、CPU ×4。
- 每次新 context，禁用 cache，阻止 service worker，正常动效。
- Chromium `155.0.8059.85`，Node `v22.23.3`。
- 五次 LCP：**2464 / 2480 / 2492 / 2532 / 2460 ms**。
- p75：2492 ms；`all_runs_below_target=false`，**不符合每次 < 2500 ms 的验收条件**。
- `static_resources_loaded=true`；每次 18 个字体请求 / 1,069,544 B encoded，2 个 JS 请求 / 76,565 B encoded。

本批不是候选变更的收益证据。不能只引用 p75 或删除 2532 ms 那次失败，也不能通过单纯反复采样挑一批绿色报告。

### Run 1 的实际时间线

下表为导航起点起算的 `resources` 数据，时间四舍五入至 0.1 ms；字节为 encoded body，未混入 headers。

| 资源 | 开始 ms | 完成 ms | encoded B |
| --- | ---: | ---: | ---: |
| `/fonts/fonts.css` | 200.9 | 1595.5 | 62,790 |
| Sans CJK119 preload | 201.7 | 1658.2 | 76,324 |
| Sans Latin preload | 202.5 | 1041.3 | 24,880 |
| index JS | 203.0 | 1209.4 | 31,258 |
| React JS | 203.4 | 1410.4 | 45,307 |
| index CSS | 203.7 | 734.6 | 10,681 |
| `/api/cases` | 1748.8 | 1923.0 | 2 |
| `/api/history` | 1750.4 | 1937.9 | 2,608 |
| `/api/chart` | 1751.7 | 2429.8 | 13,804 |

两条 preload 总计 **101,204 B encoded**，约 101,804 B transfer；与 JS 76,565 B 和 render-blocking 字体 CSS 62,790 B 同时进入早期请求时段。101,204 / 200,000 ≈ 506 ms 只表示聚合带宽量级，不是承诺可节省 506 ms LCP。

Run 1 最终 LCP 为 2464 ms，元素 `P.small-text.secondary-text`，对应 Today 的 `day.method_note`；在 chart 响应完成后约 34.2 ms。Run 4 chart 为 1808.1 → 2501.6 ms，最终 LCP 2532 ms，相差约 30.4 ms。字体 CSS 在 Run 4 于 1603.7 ms 完成。

从请求时序推断，减少不必要的早期预加载竞争，或使常用切片优先级低于关键入口，可能提前 CSS/JS 完成及后续 API 启动。**这是可检验推断，不是已证因果**。18 个字体请求中许多在 LCP 后才完成（Run 1 最晚约 6950.5 ms），不能把“全部字体完成 6.95 秒”当成 LCP 阻塞时间。`api/client.ts` 已有 `priority: 'high'`，不重复宣称新增该项能带来收益。

## `low` 提示的本地证据限制

- 已有报告给出 Chromium `155.0.8059.85`，但未记录 `Network.requestWillBeSent.request.initialPriority` 等实际优先级信息。
- 本地 `node_modules/typescript/lib/lib.dom.d.ts:15168–15172` 声明 `HTMLLinkElement.fetchPriority` 为 `"high" | "low" | "auto"`；这是工具链类型支持，不能单独证明实际浏览器调度已按提示执行。
- 本地 Playwright CDP 类型包含 `initialPriority`，当前性能报告未采集这个字段。此次只读调查没有启动浏览器去检查运行时属性或调度。
- 后续以同口径五冷的资源时序和 LCP 实测为准。提示被忽略也不能降低阈值，不能把文件中出现 `low` 当作性能收益。

## 离线 CSS 范围规范化：收益太小，丢弃

既有 `prepare-fonts.mjs` 只压缩 CSS 空白。本次用已有 Node 和 `gzipSync` 对每个 face 的 unicode ranges 排序、合并相邻/重叠、去重并统一小写进行离线算术比较，没有写出候选 CSS：

| 指标 | 当前 | 离线候选 |
| --- | ---: | ---: |
| faces | 202 | 202 |
| range items | 18,136 | 18,136 |
| CSS 原始 B | 187,451 | 187,339 |
| gzip B | 62,790 | 62,682 |

仅节省 108 B gzip（约 0.172%），无相邻或重复区间合并收益，建议不引入这项改动。当前 CSS SHA-256：`34d2a7f58131126839c1fee72a06c4cacefe140f07914dde1025889d7a73178e`。没有二进制子集化，没有新增 fontTools/brotli 或其他依赖。

## 受影响检查与保留边界

| 检查 / 入口 | 候选影响与应验证事项 |
| --- | --- |
| `web/tests/font-coverage.test.ts:132–143` | 会读取 HTML 的字体链接，现有 `preloads.length > 0` 可由保留的 CJK119 满足。适合新增精确断言：只预加载常用 Sans、`fetchpriority=low`、不再独立预加载 Latin；不能删掉覆盖和源字节断言。 |
| 同一 font-coverage 文件的整体测试 | 仍应验证官方 package 版本、两个 family、202 faces 的顺序与描述符、每 face 原始覆盖集合、所有官方 WOFF2 字节/hash 相等及未改 OFL。不能用视觉相似替代字节/覆盖证据。 |
| `web/scripts/prepare-fonts.mjs` 与 `font-css.mjs` | 本候选不改。完整字体二进制共 10,531,532 B，原样保留；不把去预加载描述成移除字体。 |
| `web/scripts/bundle-budget.mjs` | index HTML 的字节/hash 会变，字体 CSS、静态 JS/CSS closure 仍计入。基线 gzip 总量 150,533 B < 204,800 B；全字体二进制另计，不能把预算通过等同 LCP 通过。 |
| `web/pwa.plugin.ts` 的 `SHELL_FONTS` / `selectShellFiles` | 四字体白名单独立于 HTML preload：Sans119、Sans Latin、Serif119、Serif Latin 都保留。HTML hash 变化应自然更新 shell manifest/SW 产物；不要扩缓存范围或缓存任何内容数据。 |
| `web/tests/pwa-shell.test.ts:95–125` | 继续验证只选择完整 fonts.css 与四个 shell 字体，不选择任意字体/数据；不依赖 HTML preload 数量。 |
| `web/tests/pwa-shell.test.ts:135` 及 privacy/network-only 用例 | 这里的“preload verified build bytes”指 SW 构建白名单缓存，和 `<link rel=preload>` 不同；仍须验证匿名、校验 hash、无运行时内容缓存。 |
| `web/tests/e2e/night-pwa.spec.ts` | 重建后验证安装/离线完整字体可用、白名单每个资源字节匹配、未漏字体、API/对话/无痕仍 network-only。不能删掉 Latin 离线字体来配合入口变更。 |
| `web/index.html` 与 Vite 输出入口 | 正式只做单项明确变更；完整字体 stylesheet、模块入口、全站文案、正常动效保持。源与构建产物 hash 在测量前后均固定。 |
| `web/scripts/measure-mobile-lcp.mjs` | 不修改 LCP 判定、等待条件、合成数据内容、网络/CPU、cache/SW、正常动效、资源失败检查、每次冷启动和最低五次要求。保留所有唯一 attempt 的完整报告与截图。 |

精确搜索正式 tests 的 `preload` / `fonts/fonts.css` 后，只有 font-coverage 的 HTML 字体链接断言直接依赖本次变更；`q9-v3-visual.spec.ts` 中的“preloads a persisted result”是数据夹具注释，不是字体请求约束。

## root 实施后的测量顺序

1. 独立提交明确的 HTML preload 切片；完整字体覆盖、bytes、OFL、PWA 白名单保持。
2. 运行受影响的字体与 PWA检查，重建并生成新 bundle 报告；普通入口/字体视觉检查保留。
3. 确认源与构建冻结后，单批至少五次同口径冷启动，用新的唯一证据目录。每次成功加载所有静态资源，且每次 LCP 都必须 <2500 ms 才验收。
4. 保留基线 `2532 ms` 失败与后续每批失败、全部五次数据、截图和 source/build receipt。候选不通过则记录真实结果，继续分析实际请求时序，不挑样本或调整阈值。

本笔记交付时：只有原始失败基线和离线字节比较，**候选尚未在此子任务实施或实测**。
