# 模块线：10月20日夜间与10月27日前续作

## Purpose / Big Picture

在纯本地边界内完成统一时间解析、记忆2.0、SSE核心、调度、整理v2、token/流式Outbox，以及接线说明；随后完成储备池、白天追加和33号模块队列。模块只计算候选或通过注入端口运行，不修改现有运行入口，不访问服务器、真实模型或飞书，不下载模型，不合并PR。每项先测试、再提交/普通推送、写小回执。不能把替身或内存状态当作真实接线验收。

## Context and Orientation

唯一工作目录 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`，分支 `v4/mod-organize`，启动HEAD `8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd`。该提交已有117个上一轮新增路径，本轮视为既有文件，不再修改。新模块/测试/文档使用新路径；本轮新增文件可在实现内迭代。相对本启动HEAD只允许A，不通过merge/rebase引入修改旧文件。33号允许集成merge的通用规则不覆盖用户对模块线的只新增限制，需要接线的改动留主线。

只读复用：`timekit/clock.py::Clock/FrozenClock/SystemClock`；`calendar_cn.py::day_status/statutory_dates/holiday_window`；`almanac.py::almanac/solar_instant`；既有memory源授权与slots设计；旧followups规则的scope/source/cap/quiet；旧CardKit未知不重发；旧Outbox freshness。origin/v4/main仍b9a89b6，P2历法已在本树，不复制节假日表。不得改旧工具名、原话、撤销、owner隔离或readonly源码。

设计真相源为脑目录28（第一节、K1–K5、Z6、事件v1、公共规则）、02§6/§9、18/P5与P7增补、22号。首次读指令板mod.md为v1（文件自标写入时间晚于读取时实际时钟，版本有效但不伪造本地执行时间）；顺序明确为28主/储备→29〇-B模块白天追加→33第四节→无尽储备。公共规则不新增依赖。

## Progress

- [x] (2026-10-20 22:48 +08:00) 核对干净HEAD与分支，读28必读章节/AGENTS/PLANS，启动U4核心、只读历法适配、独立验收三个代理。
- [x] (2026-10-20 22:55 +08:00) 已执行指令板 v1：确认并排入其规定顺序；已建立当前聊天20分钟续作自动化，截止10-27 22:00北京。
- [ ] Q1 U4：≥300测试，基准10-17+五参考日、正反各20、候选/绝对化、属性与性能、接线指南。
- [ ] Q2 记忆2.0：去重合并/冲突/敏感先问/重要度衰减/八分节提案/过期归档C2/撤销。
- [ ] Q3 SSE：冻结事件v1、seq/serialize/coalesce/replay、15秒心跳、24小时清理计划、reset、内存/PG端口。
- [ ] Q4 调度：工作日/调休/农历循环，K1晨报、K2到点与迟到；日限/来源/quiet保持。
- [ ] Q5 整理v2：盲评B先独立冻结、调参不看；ngram/词表/平滑/待整理；最后独立评测准确率/弃权率/ARI。
- [ ] Q6 P9：K3 token有效期纯策略、新Outbox流式意图/租约/命名空间合并；K5字段仍待核实。
- [ ] Q7 各模块新接线指南；不覆盖上一轮指南。
- [ ] 储备：资料相对日/英文、性能tracemalloc、U4→记忆→过期→提醒组合、异常与覆盖。
- [ ] 10-21 07:30收尾并08:00前首夜汇总，之后继续，不终止本周任务。
- [ ] 白天追加：晨报编排/P5b余下纯模块/跨模块属性/整套三遍稳定性。
- [ ] 33第四节：保持草稿CI/P9官方复核候选/52+SP新脚本素材/record_only校准工具/四周期报告/dry-run导入/反思与画像/储备。
- [ ] 10-27 22:00北京前持续推进，最终安全checkpoint后暂停自动化。

## Surprises & Discoveries

28号提供上一夜停机的系统日志复核，不能再将小时空白解释为任务提前做完。主机显示时区可能东京，本轮所有时间从UTC明确转换Asia/Shanghai，测试注入zone。指令板v1文件标记00:10，但当前UTC换算仍为10-20晚；按实际工具时钟写执行记录，版本号作为版本号处理。

未完成的旧模块存在设计更新：旧brief被quiet顺延08:30，K1改为订阅时刻默认07:00豁免；旧token默认15分钟只是候选，K3按动作类别24小时/高风险15分钟。本轮只能新增策略/适配器，不修改旧源和旧测试，指南必须指向新版入口。

## Decision Log

记录/调度口径固定Asia/Shanghai，显式优先于客户端Tokyo；不改系统时区设置。所有人工决定缺口写日报，继续独立事项，不等离线用户。指令板不能扩大服务器/真实调用/飞书/合并/数据删除授权。涉及实际数据删除的策略只产出清理计划，不执行删除。

续作自动化id `10-27-22-00`，ACTIVE、每20分钟唤醒本聊天，截止2026-10-27 14:00UTC；不改变其他线自动化。自动化和本机日志都依赖机器可用，恢复时据HEAD/计划/日报断点继续，空档照实记。不创建后台自动git提交器，root统筹提交以避免代理未完代码被混入。

测试最多四进程；root、三个代理各最多一个。全量模块回归只在北京时间每小时45–60分启动，非时段只目标测试或继续实现。每40分钟至少一个有意义测试/提交/推送checkpoint，部分实现用wip且回执标未完成。不用空提交或无意义重复测试制造进度。

U4的天粒度point为半开日区间，精确时刻point的start=end；候选UTC aware，展示绝对日期用owner zone。未知节假日安排不得当成已公布休息。所有模糊时间必须保留候选/低置信/needs_clarification，记忆绝对化不能悄悄选错候选。

小时日志恢复测试初稿以裸字符串01:00判断是否伪造01点，误命中真实00:01:00。改为完整日期+小时前缀，保护的行为仍是“不伪造缺失小时”，没有改日志实现迎合断言；修正后再验收。

## Outcomes & Retrospective

当前完成开工约束核对与续作安排，U4在实现中。所有模块仍为离线候选，真实集成/质量/校准和本周守时验收尚未达成；随每个里程碑更新实际命令、数字、提交和风险。

## Plan of Work

先完成timeparse包，基于P2只读端口及明确参考时刻；再新增memory2规则文件，不覆写policy/服务；SSE采用新增streaming包和冻结契约；调度/K3/Outbox用新v2入口包装旧不变量。整理v2建立独立盲评B冻结记录，产品调参只读新开发语料，最后一次读取B出实际报告，失败不刷分。每项发布后更新新指南与日报。

## Concrete Steps

    git status --short
    python -m pytest tests/v4/timeparse -q --basetemp=private/mod-week/pytest-timeparse
    python -m ruff check <本轮新增Python> --select E,F,I,B,UP,SIM --line-length 120
    python -m ruff format --check <本轮新增Python> --line-length 120
    git diff --name-status 8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd
    git push origin v4/mod-organize

清provider key、关闭追踪、PYTHONDONTWRITEBYTECODE=1，TMP/pytest临时目录放本树private。复用现有Python3.11与Ruff，不安装依赖。断点元数据置private/mod-week，不写隐私正文。

## Validation and Acceptance

U4对TM01/T08/T14和KU时间写入有≥300独立用例，周三同日/凌晨歧义给候选，全部日期绝对化保留原文。memory2覆盖M/R/F/KU/C2，助手话语永非用户事实，源撤销优先。SSE各冻结事件有公共v/run/seq/北京时间ts，JSON/SSE roundtrip与Last-Event-ID隔离；核心不建HTTP服务器。P7覆盖P/PR/AX与K1/K2边界；P9覆盖token/unknown/fence。整理只报告已归类准确率、弃权比例和ARI，不用开发指标代替盲评。详列未验证主线接入。

## Idempotence and Recovery

不迁移/连接DB，不回填实际历史。所有变化只输出有operation_id/revision/scope的纯计划；实际保存/撤销/清理由主线受控事务。重启先读指令板、git和最后真实进度，保留已推送结果，不重做整夜。未知发送状态保留，禁止换business或新卡绕过。

## Artifacts and Notes

日报 `docs/v4/daily/2026-10-21_mod.md`，之后按北京时间日期；每天08:00和22:00各一次汇总。证据 `docs/v4/evidence/MOD_2026-10-21/`，指南 `docs/v4/integration/mod/*_20261021.md`。B集仅报告冻结hash，不给调参代理看内容。没有真实资料或密钥。

## Interfaces and Dependencies

TimeRangeParser由主线定义/替身，本线实际parse_time_range/absolutize为可适配纯模块。calendar只依赖本地锁定P2。PG事件端口只定义core_run_events行形状及注入事务接口，不连DB。真实event schema若origin/v4/p3-agent-runtime发布，readonly git show做契约比对，不修改对方文件。daily_transit样例仅read-only取命理线契约。

## 修订记录

- 2026-10-20 22:55 +08:00 创建本周计划、冻结本轮只新增基底、记录指令板v1/20分钟续作/K1–K5与事件契约和测试错峰约束。
