# P2 数据底座与连续上下文实现证据

仅本机 PG15.19 与合成数据，Core/Charts 独立环境，测试子进程清空模型 Key。未访问 stage/生产、未调用真实模型或真实飞书。

- 0001–0004 合成旧 schema 升级至7及重复初始化通过；未知/缺口/漂移链拒绝。运行角色实测新表 DML、迁移账本只读。
- 本地分词/simple GIN 搜索、owner/subject 隔离、删除向量清理；部分原话撤销后搜索与回填不恢复已撤回内容。
- 最近30条人生线程；用户/助手/时间/渠道与话题保留，助手不能成为用户事实；同成功运行稳定 ID 去重与修订。
- 300轮真实 PG 成功运行：dry-run 不写，apply 300次助手写入，重复0；来源 revision/content 保留。模拟中断整事务回滚后重跑12条无重复。
- fact→助手→note→profile→summary→后续run/助手/reminder 逆序多跳；旧run缺依赖反向污染；显式note账本重放；correction 保留可重算请求；无 lineage legacy 助手同闭包清理。对应 `test_p2_privacy_closure.py` 4/4，1.85s。
- Feishu显式源核验、损坏原话拒绝；10001条旧助手回填不挤掉近期用户，同毫秒100/900微秒游标无漏页，scope/session/q保留。对应 `test_p2_history_window.py`。
- 报告四类期间含 ISO 跨年/闰年，真实服务替身边界的日期/期间、此刻、历史角色与危机固定配置。对应 `test_p2_clock_reports.py`；不将配置透传等同真实 S01 模型安全行为达标。
- 最终冻结de082ce全部v4：379 passed in159.87s；最终旧Core在独立 `core_test_p2_verified` 完整553项826.169s通过。两次完整失败与单独中止进程均单列，不计入通过数，详见validation.md/receipt.md。
- 10,000消息完整 snapshot：100样本+10预热，p50=3.714ms，p95=4.155ms，max=4.896ms，早期硬约束仍在；见 snapshot-benchmark.json。
- 32个新模块/辅助文件 Ruff E/F/I/B/UP/SIM +format120 已通过，新增函数≤60行。旧业务文件只必要接线，不全量格式重排。

已知边界：history API 为兼容未回填旧时间扫描候选；消息窗口有界，run 元数据仍 fetchall，尚无海量历史接口性能声明。未来P5 writer须完整记录source/fact lineage；仅covers_until_message_id不足以保证细粒度撤销。P2未开放P5工具。

真实 T/R/M/S 比较夜间未执行，待 P1 契约 v2 基线及大脑决定。stage仅有方案。P1合并后需保留coverage==7.11.0并重生成合并后的完整哈希锁。
