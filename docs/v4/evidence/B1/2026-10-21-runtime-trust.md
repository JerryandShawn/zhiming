# B1 Core venv 元数据保护门：独立纯模型证据

记录时间：2026-10-21 10:16 +08:00（北京时间）。本片只新增未接线helper及纯模型测试，现有B3/App/Native/B7入口、固定b9包、Charts与收据ABI未改。

唯一pytest进程于10:15:29.704380启动、10:15:30.811247结束（北京时间），退出0：**43 passed / 0.13s**；JUnit为43项、0失败、0错误、0跳过。获root明确释放第4位后才启动，结束即释放，不追加目标。原始JUnit自动时间戳来自主机Tokyo（11:15 +09），不改原件；归档metadata与本文统一使用+08。

## 所证明的范围

合成Posix元数据正例和反例覆盖固定Core树、全部祖先/包叶子/.pth及配置的root所有权和无组他写；仅接受有限解释器链接与lib64→lib，拒绝借Charts运行时、循环、危险目标与特殊文件；标准pyvenv.cfg唯一system-site=false。配置读取有界，包文件仅看元数据。真实scandir接口的替身在第MAX_ENTRIES+1项及时拒绝并关闭扫描；Reader返回大目录、pending/深度/总项限制及二次lstat/readlink变更均有反例。

公开物理入口无路径/平台参数，非Linux在构造Reader前拒绝。所有正例使用内存模型，明确 `linux_filesystem_observed=false`、`package_content_verified=false`、`stage_acceptance=false`、`publication=false`。这些结果不能证明真实Linux、wheel内容、锁安装来源、系统stdlib/共享库或第三方import真实来源，亦不能反向保护控制器Python已发生的startup。没有读取包内容、执行.pth、启动候选解释器、访问Linux环境、安装、修权限或修改现有集成门。

真实PG连接、模型请求、飞书发送、服务器访问均为0。运行进程剥离供应商/PG/能力环境，关闭追踪与飞书；未记录任何环境值、私密正文或库内容。现有B1正式Linux演练 **No-Go不变**。

## 原始证据

私有目录：`C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/private/b1-runtime-trust-20261021/`。

| 原件 | bytes | SHA-256 |
| --- | ---: | --- |
| pure-1.log | 101 | c6afd7ec80719346653468097f03dac8b4c6c37c8c85de7808c97ad9883d37a5 |
| pure-1.xml | 6988 | 4d1c415b4aa9f61535325b138a60e8cd521317f064eea55ae26b7730cf32a230 |
| pure-1.json | 876 | 9ee4eea73b22cf62abcadc936760edaa3a2e408275f8ea2cced16bf50c24ca2a |

执行目标：`python -m pytest tests/v4/release/test_b1_runtime_trust.py -q`；完整解释器/参数/起止时间保留于metadata，无密钥或DSN。严格Ruff（E/F/I/B/UP/SIM）、120列格式、AST≤400行/函数≤60行及diff检查通过；helper227行、support81行、test272行，最长函数24行。

## 未完成与后续边界

四旧接点、B7额外实际Python入口、第三方import后置报告和generator/controller受审hash闭包只有只读提案，尚未实施。B3默认校验目前已有输入/manifest文件读取，后续不得新增默认venv/root扫描，必须仍零PG/零子进程。任何正式接线、旧夹具调整、收据字段变化及真实Linux验证另行审阅，不能以本片纯模型通过放行stage或生产。
