# 四线只读核查候选（2026-10-19 07:12）

本件供主线07:30正式汇总引用，不代替最终阶段回执。观察窗口为2026-10-19 07:10–07:12，Asia/Taipei；后续提交和CI可能变化，最终汇总应再次核对。本件只新增本文，没有改其他线文件、提交、推送、合并、联系其他聊天或访问服务器；GitHub只读查询不包含模型/渠道调用。

核查方法：各树 `git branch --show-current`、`git rev-parse HEAD`、`git status --short`、最近提交与日报/计划/证据；GitHub `ls-remote`、精确提交的Actions、PR元数据。下列本机测试数字来自各线已存在的报告，本代理未重跑业务测试。仅另核前端第3项30张截图文件均存在且SHA256与其清单一致；这不代表本代理重新视觉验收。

## 分支、提交与精确头CI

| 线 | 本机HEAD | GitHub远端HEAD | 工作树与精确头CI |
| --- | --- | --- | --- |
| 主线P3 | `fd33f94f95239b82807a655ebc19682a8c18787f` | `16bfd4f8a7abc59bafcefe4a606b5cf7f80929c2` | 大量工具/循环/隐私/信封文件未提交；远端Core成功39141201106，Timezone成功39141201056 |
| 主线P1b | `dea5fa3e9573fc2ab6985f88881d489f20f9a9e7` | `ee2e6de09da00eb2b90db79a4d3e6a2d8a1e6395` | 07:10观察时干净；远端Core失败39142228275，原因如下 |
| 前端 | `c8d3b30a340bc924ee3e5214ce454665938f8121` | 同本机 | 07:10观察时干净；前端39175357854与Core39175357809均in_progress，不能用此前绿替代 |
| 命理 | `6cd04ad0fcb2bedaf6183525b495391c58c64ec2` | `d132c1b175b5cc57fcf17bc5ecf778ff6ffe73d4` | M4绑定/技能/独立研究等未提交；远端M3 Core成功39141716204，不覆盖未提交M4 |
| 模块 | `dfcd700b6b444b37208a0934fefac81f021eb50c` | 同本机 | 加分接线文档/性能/审计/测试及日报未提交；远端Core成功39142007550 |

P3/P1b的本机与远端SHA差异有主线日报中的等价tree发布记录；不据SHA不同判断代码丢失，也未reset/rebase。命理M3记录本机`24725cb`与远端代码`a61abc1`的完整tree相同，随后本机`6cd04ad`/远端`d132c1b`各有文档发布记录；本代理核对到了这些报告和实际远端头，没有独立重造远端tree来验证其全部字节。

07:10只读远端：`v4/main=b9a89b6f84f7bebb640de080548010859aae630c`、`main=b996f420bcc6c5020c14b1ff66ed13b453d901d2`。PR [#5](https://github.com/JerryandShawn/zhiming/pull/5)、[#6](https://github.com/JerryandShawn/zhiming/pull/6)、[#8](https://github.com/JerryandShawn/zhiming/pull/8)、[#9](https://github.com/JerryandShawn/zhiming/pull/9)、[#10](https://github.com/JerryandShawn/zhiming/pull/10)均经GitHub元数据核为open、draft=true、merged=false。本件没有触发重跑或修改PR。

## 必须保留的失败：P1b旧Core版本断言

[Core run39142228275](https://github.com/JerryandShawn/zhiming/actions/runs/39142228275)的job117718817728，在“Core service and calculator checks”失败。553项旧Core测试运行658.242秒，唯一失败为：

```text
test_core_memory.MemoryPostgresTests.test_versioned_schema_checksum_rejects_modified_applied_migration
tests/test_core_memory.py:276: self.assertEqual(verified['version'],7)
AssertionError: 8 != 7
FAILED (failures=1)
```

P1b已新增0008，旧校验和防篡改测试仍硬编码7；后续前端/v4/ModelPort工作流步骤因此skipped。应由主线在Decision Log说明版本期望调整，保留原“篡改已应用迁移必须拒绝”的行为断言，并补真实隔离PG定向回归；本件没有修改测试。810项本机v4绿不能替代这次失败CI；修复新头后须重新查新头结果。

## 主线：可交付子切片与未完成边界

已有发布证据见同目录 `2026-10-19_main.md`、`../execplans/P3_agent_runtime.md`、`../evidence/P3/2026-10-19-first-tools.md`和`2026-10-19-context-layers-d2.md`。

- Context/D2子切片远端`6d1d9c6`：98项目标回归、2项300轮/万消息压力通过。完整输入计量有estimate/upper/actual分离；会员可信tokenizer/framing缺失继续拒绝真实发送。压力中的18,411是策略单位，不能说已经证明Kimi真实token上限。
- 第一批七工具远端`9f56c70`：136项真实隔离PG相关回归通过；来源/事项/版本/首次步骤参数绑定与撤销投影已核。U4只是解析器注入协议，统一parser及正反各20未完成，不能称夜M2完整完成。
- P1b U38远端`18352da`：736项相关回归；中央并发/额度预留与持久全停核心。U39远端`ee2e6de`：810项相关回归；同轮推理/签名、跨用户轮隔离、thinking/effort政策与体积守卫。真实HTTP各入口守卫尚未全接，实际k3-256k/服务端effort/等价性未验证；新发现Core失败见上。
- B1离线入口远端`16bfd4f`：28项替身通过，增量入口、Hermes wrapper草案和磁盘选项齐。真实Linux/PG恢复/权限/容量尚未验证，仍No-Go。B1候选保持`b9a89b6`，tzdata随B2；扩容或清理由用户白天决定。
- 未提交的第二批工具、U7、快照、LoopCycle、core4及隐私改动，仅按07:10源码存在登记；最终测试/发布由主线及其当前代理收口。不能把文件存在算完整AgentLoop、提交闸门或所有读取端兼容完成。M5、M7、M8与P5b B仍不得根据队列推断已交付。

## 前端：三项已推送，正式后端仍有缺口

目录 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p10`；计划在 `web/ExecPlan_overnight_2026-10-19.md`，夜报 `docs/v4/daily/2026-10-19_frontend.md`；证据 `web/evidence/2026-10-19/01–03_receipt.md`及同号checks。

| 夜间项目 | 已推提交 | 报告中的验证 |
| --- | --- | --- |
| 对话事件/提问/决策/记忆卡 | `6bfeb812584d6661ad2c8087c66390eb674b510f` | 316单测；174浏览器回归；12本机PG契约；最终10项夜间复测；22张截图 |
| 独立无痕会话/退出清空 | `c72e58e739b639dbdc9f7d2dcdb6ca51b7bdb728` | 329单测、80旧页、19夜间E2E；18张截图；24小时到期、普通会话恢复和迟到回调隔离 |
| 八节画像/共享记忆管理 | `c8d3b30a340bc924ee3e5214ce454665938f8121` | 378单测、41夜间E2E；30张截图；来源范围删除二次确认、共享回执、防旧事件复活 |

各项报告Axe违规0、朱砂≤3、演示入口API/外域/console/pageerror均0。第1项本机PG证明既有v3相关契约；第2/3项的无痕/画像/proposal/源级联等正式API未交付，模拟聚合不能算后端授权或真实删除验收。飞书UA/键盘是浏览器仿真，无真实SDK/设备吊销/飞书投递。完整P10未完成；夜间队列4–7在07:12计划中仍未勾选。

## 命理：M1–M3已发，M4与独立研究未提交

目录 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p8`；计划 `docs/v4/execplans/P8_meta_parallel.md`，夜报 `docs/v4/daily/2026-10-19_meta.md`；证据在 `docs/v4/evidence/P8/`。

- M1审校38条候选规则、具名四化/时间口径和技能；报告769/769、脚本80/80、自检48/48，141保护文件不变。三条新增格局各保留三子条件作复合候选，总数38；是否符合大脑表现形式仍待确认，不能当38种已成立格局。
- M2 chart_compute契约、Schema、三体系合成原生样例：报告816/816，新增预览47项，前端引用68次解析。主线工具/持久别名/API未接；样例是草稿交付，不是现实预测证明。
- M3 E2 2025赛季清单：80题纳入14、排除66，全来源360分母另列；14题题面目标年均非2025。5个案例跨年、13组12单例导致严格安慰剂不可行，固定种子拒绝，0重抽或跨年兜底。3合成题/3隔离排盘/30脚本回调，真实模型0，专业题库分数及区间为null。报告843/843、0skip、117.12秒；远端`d132c1b`精确头CI成功。
- 未提交M4修复了canonical合成样例外层请求与原生日期/出生参数绑定不足；99项定向通过。固定合成白名单不是任意用户请求验证器，不可直接照搬到主线API。八字10章及SKILL版本/待核21项通过，仍草稿。独立规则核查、太阳时边界和性能报告也尚未发布。
- 未提交性能：各体系预热1次、10次观测，总中位八字1.134835s、紫微1.124546s、西占2.674804s，输出hash稳定；含计算/校验/序列化，不含HTTP/并发/模型，不是线上SLA。
- 保留风险：倒推E-R1旧0/10，experimental_frozen默认隐藏；原刊/异本尚有待核。独立均时差42个贴边探针有5个日/时柱差异，需白天决定边界提示，不能因秒差小声称交界可靠。

## 模块：四队纯模块已发，接线加分尚未提交

目录 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`；计划 `docs/v4/execplans/MOD_2026-10-19_overnight.md`，夜报 `docs/v4/daily/2026-10-19_mod.md`，证据 `docs/v4/evidence/MOD_2026-10-19/`。

- Q1整理纯模块：600条开发语料明确片段97.08%、ARI0.729；独立98条盲评消息准确率30.61%、ARI0.0295，**泛化未过**。仅可供人工审阅候选，不能自动整理真实历史。隐式旧topic撤销复活另加26回归后修复`a59597a`，整理最终148项。
- Q2校验纯模块880项：13类旧lint只告警、结构/严格critic v2解析、程序verdict、独立材料与κ/Wilson/macro-F1。没有真人校准、实际critic请求或Agent接线。
- Q3主动/自主纯规则276项含4000组种子随机检查：静音、免打扰、日限、敏感预览、24小时反复等。没有调度器/实际通知；D4时长守卫默认关闭。
- Q4候选卡片/action-token/CardKit替身200项；四队组合1504项/3.40秒，82新增Python静态绿。最后代码`b2924e5`，文档头`dfcd700`且精确Core CI绿。外部字段明确待官方核实，内存Store/快照不等同PG事务、跨进程租约、Outbox或真实Feishu验收。
- 四份 `docs/v4/integration/mod/Q*_wiring.md`、性能/纯新增审计及相关测试已在工作树但未提交。07:12实查 `timekit/relative_dates.py`、`timekit/parse_time_range.py`、`models/quota_guard.py`在该树均不存在；不得把模块整理队列理解为U4统一日期解析器已交付。

## 日志连续性与待决问题

主线实际小时行是22:04、23:07、07:09；不能补造中间小时。前端ExecPlan明确23:58到07:09约七小时无执行证据，原因未证实；模块日记最后小时00:00、命理最后小时23:00。本件只登记观察到的日志缺口，不能由文件时间/队列推断各线在空档内持续工作。

正式汇总应保留：可信会员token/framing与P1b全部物理入口；U4统一解析及测试；core4/run事件/present_options/review字段契约；P5b B迁移编号与主线实体；无痕长期写入范围；E2严格安慰剂不可行；模块ONNX资源与盲评失败；07:00晨报与22:00–08:00免打扰默认冲突（模块暂顺延08:30）；action token期限/官方飞书字段；命理规则复合表现/原刊与太阳时边界；B1磁盘选项及后续授权B。

四线记录均不支持宣称阶段整体完成。真实模型质量、stage/生产、真实Feishu端到端本夜未验证；后续实测仍须用户在线明确开始，部署/发送另按具体授权。
