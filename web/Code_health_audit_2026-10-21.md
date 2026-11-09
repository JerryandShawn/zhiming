# Day④ 前端代码健康只读审查

审查基线：工作树 `zhiming-v4-p10`，分支 `v4/p10-frontend`，读取时HEAD为 `a93541d52d1a1f608af936e58f7a6ea9431f25f2`。只读源码、导入、配置和既有测试文本；未运行类型检查、lint、单测、构建、浏览器或HTTP。仅写本ignored审查记录，不修改正式文件。root的性能证据目录仍有未跟踪输出，属于其在途工作，本审查未碰触。

结论：有一处可确证且范围很小的私有map清理，另有一处可选的测试警告过滤简化。没有证据支持删除整份兼容模块、测试、来源JSON或样例。这里不是全量可达性工具报告，也不把已有静态阅读当成新回归通过。

## 可安全考虑的小清理

### 1. NightApp 的三个被显式分支遮蔽的lazy map项

位置：`web/src/night/NightApp.tsx:19` 的私有 `otherPages` map；具体为 `chart` 第21行、`me` 第24行、`settings` 第25行。

证据链：

- 第85行只把map选中项暂存为 `Other`，lazy factory本身不会因此渲染或执行import。
- 第170–175行在最终 `<Other>` 第177行之前，分别对 `page === 'chart' / 'me' / 'settings'` 无条件渲染 `SampleChartPage / AboutMePage / SettingsPage`。
- 所以这三个page值都无法抵达 `<Other>`；其余值选中不了这三个key。map未导出，也没有其他读取或迭代副作用。

可建议动作：只删除map中的这三个属性。保留 `today`（第31行别名与兜底仍用）、`tarot`、`cases`；保留所有被引用模块文件和App里的真实入口。无需改路由名、给NightApp加key、移走父级port或会话hook。也不要声称这会减少多少bundle字节：同一模块在App的其他合法入口仍可达，本审查没有测量性能收益。

现有验证可覆盖夜间命盘/Me/Settings/Today/Chat路由、边界恢复、草稿/回执状态保留；root可在计划中的回归统一验证，不需要为删除三条未达属性新增镜像式测试。

### 2. 可选：PWA字体console过滤已被零字体失败断言盖住

位置：`web/tests/e2e/night-pwa.spec.ts:72–86`。

当前先从 `record.fonts` 建allowed集合，再过滤完全匹配离线字体网络错误的console消息；但同一afterEach第85行又明确要求 `record.fonts` 等于空数组。因此任何能进入允许集合的消息，都已经伴随一个必定失败的字体断言，现有过滤没有把这类失败放行。

可建议动作：若root做测试代码简化，可去掉 `allowed` 与 `unexpected` 过滤变量，最后直接 `expect(record.console).toEqual([])`。必须保留 `record.fonts === []`、字体失败annotation，以及blocked/external/pageerror断言。这样语义更直接，不能借“清警告”降低字体离线断言。未在本次审查改动或执行。

## 明确保留的入口与兼容边界

- `main.tsx` 仍真实挂载Theme、QueryClient、PWA/OfflineBanner和App；`App.tsx:8–25` 的 `pages` 静态预览与 `livePages` v3接口分支均可通过显式入口到达。`?preview=1`、`__design`、`?components=demo`、`?spaces=demo`、`?tools=demo`、`?night=demo` 不是根据目录名就能认定的临时死代码。
- `App.tsx:36–42` 的memory/timeline/graph/dict/reportsettings旧链接重定向仍是兼容行为；`live/LegacyPreview.tsx` 由 `live/Me.tsx:90` 使用，保留旧版只读档案显示，不能因命名legacy而删除。
- 旧 `components/Charts.tsx`、`Calendar.tsx`、`Composer.tsx` 与 `pages/*` 仍被可达的静态预览/Design页使用；`styles/pages.css` 第1–3行还导入messages/charts/design样式。未把静态预览组件误认成新版charts/chat组件的重复弃用实现。
- `spaces/ChatPreview.tsx:8,24,87–131` 在study区真实接入 `StudyWorkspace`；新研习模块不是只有测试导入的孤岛。
- `chat/events.ts` 的legacy路径与严格v1路径有明确输入分界，v1带版本字段时不降级；不能为“去扩展”合并或删掉旧格式读取。`chat/v2.ts` 虽未被生产Chat调用，仍由 `chat-events.test.tsx`、`legacy-v2-privacy.test.ts` 和 `tests/fixtures/v2.tsx` 使用，且是用户授权过的隔离模拟客户端，不能当成无用文件删除。
- `chat/reducer.ts:26–29` 的deprecated `withReviewPending` 是明确兼容导出，`chat-envelopes.test.tsx:243–252` 验证其终态不会再进入复核；不因deprecated注释直接删。
- `night/today/index.ts` 的barrel由 `night-today-port.test.ts` 消费；`night/recovery/index.ts` 与纯端口导出属于稳定边界，不因应用走更具体路径就自行删出口。
- 所有公开计算/学习/工具样例和provenance未改，原Schema、资产导出器与独立来源核对均不在清理范围。

## 警告与私有helper审查结果

- 在 `src/`、Vite与ESLint配置文本中没有发现 `eslint-disable`、`@ts-ignore`、`@ts-expect-error`、生产console.warn/error覆盖或Rollup onwarn吞警告规则。没有可据此删除的生产warning suppression。
- `tsconfig.json:8,15–16` 开启strict/noUnusedLocals/noUnusedParameters，这是现有约束，不是本次重新运行通过的证据。本次手工阅读未确证独立未用的私有helper，不为了给健康工作凑删除数而猜测删除。
- `tests/night-chart-projector.test.ts:2` 的唯一ts-expect-error用于导入无声明的Node ESM投影脚本；导入真实函数参与引用、隐私与Pointer测试，不能删测试或注释来冒称清零。
- `tests/route-error-boundary.test.tsx:79–81` 的console.error spy用于故意抛出的React/jsdom边界错误；它不属于生产日志吞并。若未来收紧，应记录并断言预期错误类别，而不是本次直接去掉后让正常预期错误淹没输出，也不能删掉错误注入覆盖。
- `tests/e2e/night-recovery.spec.ts:80–111` 只对固定同源模拟断线URL、精确net::ERR_FAILED文本计数，且要求console计数等于实际requestfailed计数并至多1。该例外与真实断线模拟耦合，保留；没有扩大成任意网络错误过滤。
- 普通night/components/视觉矩阵helpers仍收集全部console与pageerror并要求空。静态搜索未发现正式E2E再使用 `serviceWorkers: 'block'` 绕开正常注册；不建议为回归安静新增此类开关。

本记录只提出候选，由root在Day③及当前性能/回归冻结解除后决定是否落实。没有提前宣布Day④清理完成、三轮稳定性通过或PR验收。
