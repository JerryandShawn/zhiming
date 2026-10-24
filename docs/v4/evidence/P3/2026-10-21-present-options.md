# P3 present_options 公开链路候选

2026-10-21 01:11 北京时间。本机 Windows 隔离 PostgreSQL15（loopback55480）和显式 ScriptedPort/合成计量。清供应商凭据、关闭追踪，HTTP和外部子进程由fixture拒绝。没有真实模型、服务器或飞书发送，也没有分支合并。

## 实际行为

`agent_options.load_options` 只读取同owner/run/epoch、kind=tool、name=present_options、completed且error为空的真实PG步骤，取最后ok=true；后续失败步骤不能覆盖先前成功卡。结果结构损坏或含未授权效果时失败关闭。卡片ID和选项ID由真实run/epoch/seq确定，不能由模型指定。

工具当前可逆性是自由文本；只有值精确等于easy/partial/hard/unknown才保留枚举，其余保守映射unknown。不会把“可逆”等自由表述升级成确定easy。旧工具没有unknowns输入，本片填空列表，不编造未知项、不扩冻结公开Schema。收益、代价、风险、第一步仍保留实际工具文本。

Finalizer逐字段校验卡片引用；无效别名不能公开。保存声明必须由该字段实际引用的实体的真实saved回执支持，一条无关saved回执不能授权整卡。只在卡片出现的事实/专业引用也合入message和core4血缘，继续按实际实体/版本/人物/撤销状态核查。危机或U41模板路径不公开此前决策卡。

critic输入包含实际规范卡片；quote可来自规范卡片JSON正文。持久proof同时绑定实际工具输出hash、规范卡片hash、审阅材料hash，以及真实critic模型步骤所对应的原请求快照/指纹。pass才能保留卡片；revise最多一次文本改写，并抑制原工具卡。改写失败导致review=skipped时，程序仍从实际critic行复核revise并抑制问题卡。评审不可用或无效时，结构有效卡片按既有skipped策略保留。

真实提交后才发送present_options；事件对象与最终core4.options完全相同，最终final也来自持久成功信封。运行时与订阅恢复竞争时按run行锁复用原seq，各一份。缺卡片/final事件可从已提交信封补齐；不同内容或损坏已有事件明确拒绝覆盖，不重建已撤销正文。

## 验证

新增 `tests/v4/agent/test_present_options_runtime_pg.py`：**16 passed，7.53秒**。覆盖完整Loop真实工具→Finalizer→core4→公开事件→并发回放；最后成功卡、后续业务失败、failed/error标记步骤、旧epoch、提交前拒绝发卡；critic pass/卡片quote/revise成功及失败；卡片独有fact血缘；无关保存回执拒绝；proof/tool/request三种自洽篡改零提交；缺事件恢复与损坏事件拒绝。

最终相关检查含上述16项、原Runtime/恢复/Finalizer/信封/读取端/事件回放、冻结公开契约以及初始和多来源危机兜底：**139 passed，29.38秒**。唯一警告为既有Starlette TestClient的AnyIO弃用提醒。11个本片Python文件Ruff E/F/I/B/UP/SIM（120）、format、单文件≤400/单函数≤60和diff检查通过。`event_contracts.py`、events_v1及core4公开Schema无修改。

## 界限

仅为本机候选，未验证真实模型判断质量、前端渲染、生产负载、全部M8脚本或精确新头CI。没有新增迁移/依赖、没有改提示词措辞或公开Schema，也没有修改core3兼容读取逻辑。工具unknowns参数扩展留后续；当前不会推断成本/退出条件为零或完全可逆。候选文件SHA和测试身份见同名JSON；提交发布由主代理完成。
