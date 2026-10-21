# B1 授权A与P3/P1b续作阶段回执

- 分支 / 本轮代码提交：`v4/p3-agent-runtime`，远端tzdata `90849c60cf6772c1492df9465c0de745d857f54d`、Journal `a4a759fb03fd7ae1441374149ca0749eb7fdbb64`；[PR #8草稿](https://github.com/JerryandShawn/zhiming/pull/8)。`v4/p1b-k3-hardening` 远端 `d9abee00c3b348044d9587964aace91965b259c4`；[PR #9草稿](https://github.com/JerryandShawn/zhiming/pull/9)。文档收尾提交见task/outputs本轮提交清单；未合并。
- ExecPlan：`docs/v4/execplans/P3_agent_runtime.md` 与P1b分支`docs/v4/execplans/P1b_k3_hardening.md`，四个活文档段落均已更新。
- 本回执记录可核验子范围，**不表示P3/P1b完整阶段或stage验收完成**。全部时间Asia/Taipei，2026-10-18。

## 完成了什么

- [x] 授权A登录盘点：仅列本机密钥文件名/known_hosts；现有key成功，无需口令或修改SSH。服务器脚本经stdin执行，不读回私钥、口令、完整DSN、token或聊天正文。
- [x] 授权A范围：主机/固定代码/服务/模型非密钥配置、PG版本/两库schema1–4和校验和/角色权限、队列/Outbox、飞书/定时/CLI入口、磁盘与备份元数据；[安全证据](2026-10-18-readonly-inventory.json)。SQL显式READ ONLY，主动远端修改/备份/模型/发送均0。
- [x] 已写[B1具体操作单](../../release/B1_operation_sheet.md)，并将23号“B1保持实际k3、P1b后另做256k等价”补入[B1计划](../../release/B1_stage_plan.md)。先交大脑审阅，尚未申请或执行B。
- [x] Charts锁tzdata2026.5 / IANA2026e，独立哈希安装锁、21边界金标/5项回归与Windows/Linux CI；[证据](../timezone/2026-10-18-package-parity.md)。不改排盘算法、P8或前端。
- [x] P3 Journal原语：租约/epoch/owner/取消/截止保护、稳定操作号、已完成重放、冲突拒绝、真实副作用崩溃恢复与已登记来源撤销后拒绝正文复活；[39项证据](../P3/2026-10-18-journal-slice.md)。合并复核上下文+Journal为102项通过。
- [x] P1b M2a请求预检：K3非法工具选择零POST拒绝，单工具required，声明sampling_fixed时过滤采样；以最终httpx JSON字节检查K3默认1.8MB，再meter/count/send。非K3仅显式限额时启用，保持旧大包行为。新138+相关旧244通过，独立只读复核无阻断。
- [ ] 授权B stage部署/备份/迁移/回填/恢复：尚未授权，未执行。
- [ ] 完整P3/P1b：loop/计费与依赖/提交/API、可信token、U4/U7接线、U38跨进程守卫和完整U39仍未完成。

## 评测分数与检查

本轮真实模型、probe、评审、E1/E2、飞书发送均0。未运行新的脚本80场景或真实质量评测，不能把此前80/80及基线成绩移作本次源码质量分数。

| 检查 | 本轮证据 |
| --- | --- |
| Journal真实本机PG | 39/39，9.52s；崩溃窗口、跨连接/线程、失效正文不复活 |
| P3 agent目录组合 | 102/102，70.81s，零跳过；63上下文+39Journal |
| P1b新请求预检 / 相关旧模块 | 138/138，0.31s / 244/244，0.96s；仅MockTransport |
| 本机时区 | 5项回归通过，Core/Charts各21边界，摘要`f66f063a04cb9fb1a5238bac645d1aaea32957502bd3bb782c670ac5df578df2` |
| 双系统CI | [39119854074成功](https://github.com/JerryandShawn/zhiming/actions/runs/39119854074)，Windows和Ubuntu均通过相同摘要；只证明包数据/ZoneInfo范围 |
| 静态检查 | 本次Python文件Ruff/format120、AST边界、UTF-8/LF及diff检查通过 |

完整Core/v4/覆盖率的旧日志与本次不同源码，仍作为历史证据；本次最终分支Actions另核，不借时区CI冒充全部阶段CI。

## 改了哪些关键文件

B1计划、操作单及安全证据；Charts锁、`tools/timezone/tzdata.lock`、`tools/verify_timezone_data.py`、时区测试/workflow；P3 `agent/journal.py`及两组真实PG测试；P1b `models/request_policy.py`、两协议适配器、transport及两组替身测试；两分支ExecPlan和证据。没有改`web/**`、P8算法/skills/knowledge或模块线拥有的quota_guard/relative_dates。

## 数据库迁移与回滚方式

本轮新增迁移0。Journal复用0005步骤表；真实PG测试仅本机独立schema，不连接服务器写入。线上两库仍为1–4。服务器A没有创建备份、库、角色或运行应用，故不存在本轮服务器变更回滚。

未来0005–0007无down；旧7dbc包不能直接读schema7。操作单规定最新一致备份、停写、向前兼容修复和单独获准的恢复库演练；schema4备份先核前缀，再于恢复副本迁7/重授后重放最新撤销/收据，不启动恢复库Web。

## 偏离设计的地方

无架构意图变更。按用户本轮明确授权仅放开Charts锁/时区检查；不把它静默加入固定b9包。Journal和M2a均明确为子范围，不用桩代码冒充完整Agent或守卫。非K3默认体积限制已在复核后收窄，保留既有供应商行为。

## 未验证 / 已知风险

rootfs只余约0.737GiB是部署前置阻断；当前备份仅看元数据，没有恢复保证。stage已有历史/17个owner，不可当空测试库启动。Hermes Core wrapper也固定旧7dbc，生产切换需受审的完整增量入口方法。stage迁移/回填/恢复、生产、真实模型质量/新256k等价、全Charts算法双系统一致性、5433身份均未验证。

Journal未接loop/Toolkit/ModelPort/计费依赖/提交/API/清理；P1b完整reasoning/签名/effort/默认caps与U38/人工批次入口未闭环。两PR保持草稿，最终CI状态另见本轮提交清单，不标整个阶段完成。

## 需要用户或大脑决定的问题

先交大脑：容量扩容或受审清理方案；固定b9是否将tzdata修复单列后续；授权B的历史stage owner/合成Web/测试/恢复库与服务具体范围；Hermes增量固定入口及stage撤销重放方法。D1/D2模型决定已经明确，不重新提问。

大脑审后才申请授权B；生产维护窗口、live的2个owner范围和恢复权限在stage签收后另定。当前无需再提供登录秘密，不请求把任何凭据发到聊天。缺开始授权则保持0真实，继续本机P3/P1b与已知独立里程碑。

## 建议后续

按操作单先审前置项与精确B范围，继续P3最小模型工具闭环和P1b剩余协议/模块守卫接线；完整ContextEngine后才进入P5b B。前端/命理/模块独占范围不接管；所有真实调用依旧由主线、用户在线逐批明确开始后执行。
