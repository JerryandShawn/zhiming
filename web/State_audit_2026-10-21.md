# 页面状态审查（2026-10-21）

审查基点：`cb1213d`；2026-10-21 北京时间。初次只读审查核对18个页族与已有测试定义，随后针对发现的问题实际验证68单测、18浏览器、14最终截图，类型/lint零警告/构建通过，详见 `evidence/2026-10-21/state_audit_receipt.md`。下表的测试关系不等于每一条都在修复后重跑；完整911/530属于修复前cb1213d。同步内存演示不添加虚假的异步 loading。

| 页族 / 入口 | 当前空、加载、错误、恢复行为 | 对应证据定义 |
| --- | --- | --- |
| 全局路由 / 分包 | Suspense 骨架；导航壳保留；安全错误文案、焦点、回今日 / 真正重新载入；路由和模式变化清旧错误；普通对话控制器在夜间页边界之外 | `tests/route-error-boundary.test.tsx`；`tests/e2e/night-route-recovery.spec.ts` |
| v3 对话历史与普通草稿 | 首次加载；已确认历史在重新读取时保留；失败可再读；分页和手动重试不互相取消；不恢复 / 重发会话；草稿与附件不被历史 GET 清除 | `tests/chat-history-retry.test.tsx`；`tests/e2e/night-history-retry.spec.ts` |
| 夜间对话 / 插话队列 | 本地模拟；流式进行、停止、失败重试、排队 / 取消 / 继续；FIFO；空队列隐藏；处理按钮移除后焦点恢复已有本轮修复 | `tests/night-queue-conversation.test.tsx`；`tests/night-continue-focus.test.tsx`；`tests/e2e/night-reserve-keyboard.spec.ts` |
| Ask / 决策 / 回执 / 工具状态 | 待确认不冒充已保存；异步回执有效后只读；未知失败保留原尝试；409 等明确拒绝可改；缺能力时禁用并说明 | `tests/chat-interactions.test.tsx`；`tests/chat-memory-interactions.test.tsx`；`tests/v1-interactions.test.tsx` |
| 无痕 | 独立临时会话；离开时暂停；退出清空临时内容；普通草稿不被并入；无痕不读共享记忆 | `tests/night-privacy-components.test.tsx`；`tests/night-privacy-session.test.ts` |
| 夜间今日 | 加载 / 空结果 / 错误重试；日期清空为输入提示，不发空日期读取；过期日期结果不回流；安排与选择日期相互独立 | `tests/night-today-page.test.tsx`；`tests/e2e/night-today-input.spec.ts` |
| v3 今日 / 命盘 | 每个真实只读资源独立 ResourceState 与重读按钮；无记录有空态；资料缺失给核对入口；公开盘面投影不回显私有出生字段 | `tests/live-data-pages.test.tsx`；`tests/chart-boundaries.test.tsx` |
| 夜间命盘固定样例 / 组件预览 | 同步固定公开样例，无网络等待；口径、限制、隐私隐藏明确；没有数据时不编造北京差异 | `tests/night-chart-samples-ui.test.tsx`；`tests/chart-components.test.tsx` |
| 择日 / 合盘工具预览 | 静态目录加载 / 错误重试；哈希和来源失败拒绝渲染；idle、loading、unavailable、error、ready；条件 / 端口变化撤回证据与确认，不接受旧结果 | `tests/tools-loader.test.ts`；`tests/tools-ownership.test.tsx`；`tests/e2e/night-tools-boundaries.spec.ts` |
| 塔罗 | 初读loading/error/ready区分，非数组200拒绝；成功GET前禁新生成，已知运行仍可停止；同ID重开、A→B→A、会话切换与迟到隔离；manual新ID独立读取，原刷新行为保留 | `tests/tarot-read-state.test.tsx`；`tests/tarot-manual-read-state.test.tsx`；原刷新/流程测试；`tests/e2e/night-tarot-read-state.spec.ts` |
| 事项 v3 | 读取加载 / 错误可重读 / 空态；创建和进展等候写回执；409 保留草稿并读最新版本；不确定结果锁定原操作重试 | `tests/live-data-pages.test.tsx`；`tests/api-contracts.test.tsx`；`tests/api-races.test.tsx` |
| 关于我 v3 | 记忆空态；资料和记忆读取错误可重读；来源 / 修改记录按钮可再次读取；409 保留草稿；未接新版画像 / 提案明确不可用 | `tests/live-data-pages.test.tsx` |
| 关于我夜间画像 / 记忆 / 提案 | 八节同步快照、空筛选与来源不可用；两种删除/确认；本地已知INVALID/422编辑拒绝后保留可修正草稿；未知、429、其他操作保持原请求，409仍核对 | `tests/night-me-validation-recovery.test.tsx`；原组件/聚合/回执测试；`tests/e2e/night-me-validation.spec.ts` |
| 初次相识 / 出生资料 Sheet | 可暂停并保留引导草稿；出生仅 Sheet 内读取；等有效回执；422 释放待提交请求允许修改；409 核对当前资料；未知结果保留原请求 | `tests/night-onboarding-ui.test.tsx`；`tests/night-onboarding-birth.test.ts` |
| 夜间设置 / 设备 | 同步初始快照；保存中锁定；明确422允许修改；未知失败原操作重试；409 当前设置核对；设备吊销确认；渠道不允许修改时禁用并说明 | `tests/night-settings-ui.test.tsx`；`tests/night-settings-port.test.ts` |
| v3 设置 / 归档 | 真实 GET 的加载、读错 / 重读；归档无结果、无正文各有说明；报告时间表不完整时禁写；已保存与未保存预览分开 | `tests/live-data-pages.test.tsx`；`tests/report-receipt.test.tsx` |
| 功能区 / 整理审阅 | 本地同步树和空筛选；草稿操作有 pending / 回执失败；应用、整体和字段撤销均二次确认；15分钟失效重取票据；取消保留原消息 | `tests/spaces-organize-actions.test.tsx`；`tests/organize-v2-ui.test.tsx`；`tests/organize-v2-cas.test.ts` |
| 断线恢复 / PWA | reconnecting / failed / aborted / closed；已见正文保留、可手动重试；离线横幅；SW 仅应用壳白名单，对话、SSE、POST、凭据与无痕内容不进缓存 | `tests/recovery-lifecycle.test.tsx`；`tests/e2e/night-recovery.spec.ts`；`tests/e2e/night-pwa.spec.ts` |

## 新发现并修复的明确操作阻断

**P2：本地画像 / 记忆输入被明确拒绝后，编辑框锁死。**

- `src/night/me/model.ts:16` 的 `safeText` 对大于2000码点或包含出生原值键的内容抛出本地 `AboutMeError('INVALID', 422, ...)`；`port.dispatch` 在应用成功前不会替换聚合快照，拒绝为零写。
- `src/night/me/useMeCommand.tsx:52` 先保留 `pending`；catch 只有409和429分流，没有释放此明确422。
- `src/night/me/ItemEditor.tsx:50` 因 `hasPending && !conflict` 禁用文本框。按钮只会重发同一无效内容。取消重开可以退出，但会丢失需要修正的草稿。
- 可复现：`/?night=demo#/me` → 编辑“称呼与基本情况” → 输入合成的 `出生日期：…` 或程序带入2001字 → 保存。正文没有被保存，界面却无法继续改。
- 修复仅针对**本地已知 profile-edit / memory-edit 的 INVALID/422**清 pending，保留 draft；未知对象仅带数字422、网络、无效回执、429与其他动作继续保留原操作，409仍显式核对CAS。旧实现4负例失败/6保护用例通过，修后10/10及两个尺寸浏览器通过；不把取消重开当作修复。

塔罗初读则已补显式状态和归属保护。独立审查又发现“初读失败时已有运行不能停止”的新边界，现以已知runId+pending为条件保留原停止入口，生成仍禁用；新增真实GET失败→POST取消→GET取消状态的合成传输测试。68目标单测与18浏览器最终全绿；原8手动刷新断言未改。非数组顶层校验不等于完整逐行Schema。

## 明确边界与非阻断缺口

- 上表不证明在线后端、真实模型、真实登录 / 飞书设备或生产故障恢复已验收；本轮未访问这些系统。
- v3通用读取依赖既有API形状；除报告表、工具目录等特殊验证外，没有全站闭合运行时Schema。 malformed 200 的系统性加固可单列后续任务；本轮不以猜测替代可复现问题。
- v3主动联系、设备吊销、无痕、新画像 / 提案仍诚实禁用；已有夜间模拟实现，不把无后端当作加载失败。
- 固定静态页面和同步端口无必须等待的资源，不额外添加虚假的 loading / retry。
