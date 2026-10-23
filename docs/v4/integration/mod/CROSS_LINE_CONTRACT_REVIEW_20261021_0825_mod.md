# 跨线契约只读核对（2026-10-21 08:25，北京时间）

范围：模块线晨报/画像投影，对照命理线公开契约、前端公开模拟端口、主线公开 API/事件契约。
只读了程序与设计契约；未运行排盘、真实模型、服务、网络、数据库或前端业务请求；没有读取真实个人样例。
没有修改其他线代码，没有新增 P9 测试或变动已冻结源码。以下是接线差额，不能写成已上线缺陷。

## 1. 今日页的合成流日投影不是晨报编排结果

前端 `DailyTransitView` 固定三体系，`projectPublicDailySample` 要求 `highlights.length === 3`、
依据非空，并将来源固定在一个公开合成提交与 `ayuan_<date>.json`。
它明确只接收离线公开格式，`createTodayPort` 也注明未来要换认证适配器。

模块 `compose_briefing` 可以在缺失/坏 transit 时只给历法和安排，并报告 warning；
`transit_section` 只渲染已核对、受支持的命中，每体系最多两条，不承诺刚好三条或三个体系都存在。
这是合法的保守降级，不能为满足模拟格式而补造另外两体系的判断。

接线建议：真实今日页 API 直接提供区分历法、transit、安排的 sections/缺失原因；
前端允许“晨报可读但没有经验证流日”状态。保留现有 synthetic port，不能把它重命名为真实晨报完成。

## 2. 前端短依据引用不能代替后台授权链

前端 `DailyEvidenceRef` 仅 `date/documentId/alias`，lookup key 也是三元组。
当前只查已固定的合成表，没有冒充真人授权。

模块 `BasisRef` 还包含 owner、subject、source revision、path、value SHA、claim ID；
`validate_transit` 重算文档/别名/Pointer/claim 绑定。P8 契约也要求短别名只在单文档有效，
跨人、跨日、跨结果接线要重新登记。

接线建议：真实服务在认证 scope 内解析该三元组，核对当前资料 revision、来源活性及完整证据绑定；
前端三元组只能作查证请求，不能作为权限凭证或按 alias 跨文档全局查找。
公开合成的 `sourceCommit`、`integrity` 字符串不是 PG 来源授权回执。

## 3. 正午盘面快照应继续明确，不能被07:00晨报措辞放大

命理线公开契约明确 `daily_transit` 是目标日期北京时间 12:00 的瞬时快照，
不代表全天行运、进入/离开时刻或择时结果。
前端投影严格核 `snapshotAtBeijing === date + T12:00:00+08:00`；
模块文案也明确“按当日北京时间12:00快照”。这三处当前口径一致。

后续接线不得把晨报生成时间 07:00 当成 P8 盘面计算时刻，也不得把当日正午快照描述成已发生的现实结果。
依据 P8 `complete=false` 的未齐成员不能被前端摘要改成完整成立；模块现保留该限制。

## 4. 关于我的分析条目与用户事实需要显式映射

模块 `ProfileLine.origin` 区分 `user_fact/analysis`，渲染时分析明确标“推测（不是用户原话）”；
来源撤销、版本变化、无痕或当前事实无效时，即使 pin/用户编辑也过滤。

前端模拟 `ProfileItem` 目前有 text、sourceRefs、confidence、pinned、userEdited，
没有 origin；`SourceRef` 也没有说话人字段。不能把模块对象逐字段丢弃 origin 后，
将所有分析条目当成用户事实展示。

接线建议：真实 API/前端类型保留条目来源类型或独立的可见标签，原话与归纳分开；
用户编辑仍要有该次编辑的权威来源。后台先核 scope、source epoch、revision、角色和连续原话锚，
再投影给前端；前端本地 snapshot revision 不能代替当前来源授权。
命理档案第7节在模块中尚未接权威 P8 画像契约，真实适配不能以合成命盘补位。

## 5. 主线已经明确尚未发布这些真实 API

主线 `api_runtime_v1.md` 明列已发布线程/运行/事件入口，同时明确记忆、画像、提案、
主动联系、今日页、区与话题仍应逐个交契约。
因此本核对不报告“前端 API 已接完”，也不编造 `/api/today`、画像确认或日程持久化行为。

模块八节画像与前端八节字符串 ID 的映射顺序当前一致，但真实 wire 字段仍需单独契约，
尤其数字 section 与 basic/current_life/goals/people/preferences/communication/chart_summary/followups 的转换。

## 6. SSE 事件 Schema 没有语义漂移证据

模块冻结来源 `events_v1.origin.schema.json` 原始 SHA 为
`fa42065d1baebb5b486283b073f4e141ead00d8b96538254c0a4b3112916a04d`；
读取时主线 `events_v1.schema.json` 原始 SHA 为
`3351ce217e8b478554dfce0d16b98c9ee5484e90f2a4bf088c335d7356d55c42`。
两文件 JSON 解析后的对象严格相等。不能仅凭字节 SHA 不同宣布接口破坏；本次没有新增 SSE 兼容性失败。

## 来源快照（绝对路径，只读）

| 来源 | 读取时 SHA256 |
| --- | --- |
| `C:/Users/Administrator/Documents/Codex/zhiming-v4-p8/docs/v4/contracts/daily_transit.md` | `aaee393c9e8c934afbbdb768975a8a7880e4c10b26389429a829c9a114729557` |
| `C:/Users/Administrator/Documents/Codex/zhiming-v4-p10/web/src/night/today/types.ts` | `c9a8b5018f0308f7c25632b2d50739712e61d01180adefaff6c71d911b3d6d32` |
| `C:/Users/Administrator/Documents/Codex/zhiming-v4-p10/web/src/night/today/projection.ts` | `6e2561ebd857ffcbfb4899a96d53567f44b1a1024cc26fca19503b2abc201bef` |
| `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/application/briefing_v2/evidence.py` | `fe0fd74df3ac39502b0a192e76413e3cae58d9250a7fb048b9834130c2c3e7d6` |
| `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/application/briefing_v2/contracts.py` | `ba352ffde101783ca8dce41e07d132539c36f67da9cc585566e4731b71f6b53b` |
| `C:/Users/Administrator/Documents/Codex/zhiming-v4/docs/v4/contracts/api_runtime_v1.md` | `c7c9824e367c8a829174436237f7de5b1493d2c37b9d5fa75a5c7a25f14fc2d7` |

补充阅读：前端 `night/today/port.ts`、`night/me/types.ts`、`night/me/port.ts`；
模块 `reflection_v3/profile_contracts.py`、`profile_guard.py`、`profile_renderer.py` 和 `briefing_v2/transit.py`。
这里只依据当前本地文件；未查远端提交、CI、集成状态或实际 HTTP 行为，后续接线前需重新核对。

## 待决与后续（不等待离线用户）

1. 主线冻结真实今日/画像 wire 契约，再由前端线实现认证适配；模块线不改 web。
2. 真实查证接口保持 scope+当前依赖账本；前端短 alias 不授予读取权限。
3. 保守降级与分析标签的可见表达由主线/前端/大脑共同复核，缺契约时继续用隔离合成端口。
4. 未验证：真实登录、多用户会话切换、PG、HTTP、外部卡片和真实模型质量。没有把只读核对当成端到端测试。
