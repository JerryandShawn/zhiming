# 自写后继续调用工具：收口补充

2026-10-19 07:46 +08:00。组件初版只验证case_update后文字结束，第二个真实工具会因冻结来源版本旧值被误拒。新增真实PG用例先证红，再让ToolService.authority调用同一精确reconcile_versions，仅接受已完成步骤、实际回执及当前修订证明；不改冻结source_versions、不改输入指纹、不放宽未知外部修订。

新增用例验证case_update→profile_get→文字，两个真实工具都成功；原外部新修订/缺证明/注册竞态反例保留。组合80 passed/20.03秒，包含旧工具、提醒、U7、own revisions及最终提交。Ruff/format通过，authority函数35行。

这只解决前份agent-components证据中的“连续自写来源版本接线”缺口。其余RuntimePort、无痕、网关、dispatcher、U4、charts_service、所有core4旧读端、一次再生成调度与U41仍未完成；0真实模型/飞书/服务器。M4原21文件hash清单是修改前的历史快照，此次agent_tools.py变更以本补充对应提交为准，不改写原测试身份。
