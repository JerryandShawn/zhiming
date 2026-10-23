# P1b 阶段回执（离线首切片，阶段未完成）

- 分支 / 最后代码提交：`v4/p1b-k3-hardening @ 2cf6b1f1edefac46e2b5d035484713326eacf7d0`；等价不可变远端代码对象 `be8119e475034306681b6d168ab49073b2a23b76`；tree `ff652a9d1e4a8b64cd83e364aebf10be1234cb47`。
- PR / CI：https://github.com/JerryandShawn/zhiming/pull/9（草稿）；代码与证据随本提交发布，最终头CI待核验，未合并P1b。
- ExecPlan：[P1b_k3_hardening.md](../../execplans/P1b_k3_hardening.md)。

## 完成了什么（对照增补验收标准）

- [x] 标准1的离线首切片：HTTP/SSE统一分类、受控kind与不可变动作；会员429退避，不再一律当quota。78合成矩阵及adapter边界，错误→类型→动作见 [验证说明](2026-10-18-offline-slice.md)。
- [x] 标准4的配置子项：会员K3显式关思考拒绝；静态/effective env、缺key前、resolve重检、直接构造均覆盖，合法None/非会员/非K3保持契约。
- [x] 调用链边界：单层物理retry、仅显式非会员fallback、可见输出后不重播、取消/deadline与typed eval stop兼容；失败4/成功2/取消1次的factory回归。
- [x] 本地检查：Core553、models511及约95.66%覆盖、v4918、脚本80/80+48自检、transport/PG92通过；证据 [结构化结果及日志hash](offline-validation-2026-10-18.json)。
- [ ] 标准2、3、6：U38真实PG账号级账本/并发槽/跨进程持久停止和所有调用入口接线、0008迁移与授权未实施。
- [ ] 标准5：真实探针、缓存/签名/effort与256k等价性尚未获开始指令，未运行。
- [ ] 标准7、8完整阶段门：最终精确头CI待发布后核实，阶段回执明确部分完成；U39、采样/体积/tool_choice等剩余工作不能删去。

## 评测分数

脚本80/80，框架48/48（10.72s）；实测模式未运行，真实POST0，无模型能力百分比。models511/511（75.04s），903/944语句=95.6568%，coverage显示96%，95%门通过；全部v4918/918（153.58s），零skip、1项上游告警；transport/PG92/92（2.72s）。

旧Core553/553（638.777s）在同生产切片回归过程中运行，早于最终非会员HTTP402窄改；root观察退出0、日志553/OK。最终“非会员402保持BadRequest不重试”的差异另由全models/v4重跑覆盖，**不冒称全部日志绑定同一瞬间的最终源码**。

## 改了哪些关键文件

`models/error_actions.py`、`error_classification.py`、`errors.py`、`provider_diagnostics.py`定义类型/动作及受限公开诊断；`retry_policy.py`、`transport.py`、`registry.py`执行单层退避/fallback与取消边界；`config_policy.py`和Registry/adapter接线禁止显式关会员K3思考；`tools/eval/quota.py`保持typed停止分类。新增/更新的模型测试及 `tools/eval/fixtures/u37_error_matrix.json` 保护上述契约；夹具为合成数据，未放入ignored tests目录。

本次文档包括ExecPlan四个活节、验证说明、结构化证明及本回执，由root统一提交/发布。

## 数据库迁移与回滚方式

本切片新增迁移0，未实施0008，P2已有0001–0007保持不变；真实PG检查只使用本机可丢弃schema，没有stage/生产DDL。未启用新运行入口或实际切换模型，代码回滚可由root在分支回退/反向提交；不删除业务数据、不重置旧会员账本或停止文件。未来PG守卫迁移/部署另需实际方案与授权。

## 偏离设计的地方（及理由）

当前按可独立验证的离线首切片交付，完整U38/U39等保留未完成。公开诊断仅提取审计过的公开额度句，严于任意前240字，防止供应商回显私人正文。旧429/500正文quota和无类型SSE的断言按新状态/type优先设计替换，真实403、隐私、charge/repair及可见不重播不变量保留。非会员HTTP402明确保留旧BadRequest/no-retry，避免扩大Kimi会员专项策略。

矩阵内source_design_sha256指84项派生设计矩阵前身，已核对原字节；不是大脑原提示词hash。正式78项夹具实际路径及两类来源hash在结构化证明单列。

## 未验证 / 已知风险

U38中央ledger/跨进程全停、全部旧/新入口覆盖、U39完整推理回传、签名/effort、采样移除、tool_choice、体积预检、人工批次代码门、256k实际切换、真实探针与最终CI未完成；当前ErrorActions的persistent/global标记不等于已持久全停或已发通知。旧k3 E1冻结仍是未运行历史准备物，新256k执行源须另建身份。

测试的上游anyio弃用告警尚在；不因此升级依赖。阶段没有stage/生产或真实飞书端到端证据。

## 需要用户或大脑决定的问题

真实探针/等价性、每批E1/E2都等待用户在线并在本聊天明确开始；每批≤10、批间20分钟、≤80真实POST/滚动5小时，夜间零调用，不自动续跑。D1会员端点与并发/terminated全停，D2主评审目标256k，D4提醒关/无紧急联系人，D5 E2仅2025均已决定，不重复提问。

模块线quota_guard核心接口交接与中心ledger DSN/schema/account namespace接线待落实；若迁移顺序确实冲突，再交大脑裁定。本轮不为解决依赖创建假guard，不越界修改模块、前端或命理拥有的文件。

## 建议后续

root发布本切片代码及证据、建立/更新草稿PR并等精确头CI；接着按原计划完成U39/体积/工具选择和模块守卫接线。所有入口共用一个中心账本，不能在main/e1各业务DB各算80次或各取同名锁冒充全局。P3上下文守卫由对应主线工作树推进，真实探针和256k切换始终等用户的具体开始指令。P1b保持未完成，不自行合并。
