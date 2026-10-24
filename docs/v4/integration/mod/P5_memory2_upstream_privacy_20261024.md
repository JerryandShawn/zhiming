# P5 主线隐私接线（2026-10-24 03:13 +08:00）

普通合并主线 5af4628 后，memory_forget 使用主线 v4_forget；最终撤销确认由主线 agent_withdrawal_ack 校验当前租约、原始请求、操作指纹、原生删除与撤销账本后发布。本线没有改此提交边界。独立 memory2_withdrawals 服务仍供认证所选项动作及遗留服务使用。

F01/F03 复用主线原生层初始化与明确逻辑观察视图，保留 raw native_status/deleted 与真实 tombstone 证明。F02 敏感提案及原时间的助手回复仍由真实 P3/scripted Runtime 产生；原生层观察只登记这份实际 pending，不再另造 active 替身或重复导入。F04 统一用主线冻结上下文后撤销钩子，验证恰好一次 epoch 重生成和两次脚本请求，旧正文不进入新上下文。

单轮指定记忆集合 34/37；F01–F04 通过，M08/KU01/KU02 仍失败。旧失败证据保留；本机合成成功不代表真实模型质量或产品上线。

两个隔离场景目录都含 TM01：主线 core30 是 time，记忆附录 B 是 memory_recall。验证器保留两份各自类别，仅允许 TM01/TM02 记忆例外；新增目录隔离契约检查，不把两目录混成重复 ID 的同一套评分。

后续同步须核对真实远端 SHA。本仓库 fetch refspec 只跟踪 v4/main，单独 fetch 集成分支不会自动刷新旧 origin tracking ref；本次显式合并已核实的 5af4628，后续不得以旧 tracking ref 的 Already up to date 作为同步证据。
