# B1 控制器硬化子片（未完成Linux演练）

2026-10-20 22:55 +08:00，Asia/Shanghai。只改外置控制器和合成测试，不改固定b9发布包，不访问服务器/模型/飞书。

retarget现在逐字保存受保护runtime.env到operation备份，只把唯一CHART_PYTHON的受审7dbc固定路径改为b9。未知/重复/缺失路径一律拒绝，已是b9则不写；其它字节（含合成秘密字段）保持原样。Native更新本次env预期hash后再次核model，三unit/Hermes仍沿原受审范围。

LocalCommands不再从PATH选择systemctl/pg_dump/pg_restore，按固定绝对候选解析并核root所有权、不可组/他写、可执行。固定Core解释器验证真实路径但保留venv symlink调用路径，以维持虚拟环境。二进制版本与Linux真实可信文件链仍须后续实测，不冒充已验。

真实执行的目标回归：test_core_incremental_environment、upgrade、native、pg_port、cli，46 passed、52 subtests passed、3.00秒。Ruff/format通过，host392行，新增environment39行/binaries43行，函数≤60。没有整库回归。

旧Native fixture原先未含CHART_PYTHON，不符合本次切换所需真实配置；补固定旧路径，并把新增helper纳入既有明确模拟Windows 0600的测试边界，原assert全部保留，新增CHART路径与model保持断言。首次45通过/1失败来自该Windows权限模拟缺失，修fixture后完整目标重跑全绿；不改真实权限检查。

当前控制器hash：1739b7e247ca5069fa0678adcc78a2d136c050cde5d3efe412bc6eb27bf52c5f（按当时全部core_incremental*.py字节）；任何后续控制器源码变更必须重新绑定approval，不能沿用历史81216d0值。

B1仍No-Go：Docker/WSL阻塞，POSIX权限/跨exec锁/真实systemd/PG15容器/恢复回滚未验；真实B7与开门/回滚入口待独立交付。两执行单是No-Go初稿，不能据文档存在进入服务器。
