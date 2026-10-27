# v66/R48 首发 stage 第二次尝试：停止回执

实际执行：2026-10-27 17:27:17–17:33:01，北京时间。读取 main66/R48 后按37号 Go，从 B0 重做一次；候选 `e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd`，operation `4e680f175ea28cc8`。本次不再自行重试。

|步骤|实际退出/结果|
|---|---|
|本机37/SHA/clean/固定包及bootstrap/分词器六文件|0，全部匹配；没有重新打包|
|B0 前置和新目录|0；原生 LF 原始字节发送成功|
|固定公开包3文件、分词器6文件上传|均0；没有上传凭据|
|B2 解包、独立venv、锁依赖、pip check、tokenizer|均0；后台venv/dependencies均实际exit0后才继续|
|R28 回环PG15管理员|0，私有文件/认证校验通过，口令输出0|
|B3 只读复制原stage到新副本|0 / copied_closed|
|B4–B5 迁移1–8、第二回填0变化、撤销重放|0 / prepared_closed，checksum及三项repeat=0、replay_full_state_unchanged=true、model/external=0均核|
|B7 空增量备份、恢复、seal、改名对调|均0；backed_up_closed / restored_new_database / exchanged_closed；current_oid=65685，原副本OID62786保留为本operation failed库，未删除库，production=false|
|B8 runtime provision、systemd verify、admit、start|命令均0；服务active，MainPID2925721，仅stage副本获准入。verify输出其他现有unit的弃用警告，见下，按单停止|
|健康/状态/历史冒烟、实际cgroup出站正负验|未执行|
|writer负验、维护503、最终inactive/closed|未执行；不能宣称stage成功或收尾closed|

**停止原因及当前状态**：`systemd-analyze verify` 原始输出对 `/etc/systemd/system/tat_agent.service` 的旧 `/var/run` PIDFile，以及 `/usr/lib/systemd/system/ip6tables.service`、`iptables.service` 的过时 `StandardOutput=syslog` 发出警告。没有报告新stage unit未知指令；verify本身exit0，不能把它描述为unit启动失败。但执行单明确“不能忽略警告”，本次短脚本返回并检查原件后已停止，没有后续远端执行、修补或重试。新unit已active/副本已admitted；维护门及收尾seal未执行。保持现场等待大脑指令，不改其他unit。

每次SSH/SCP均显式指定现有 `gto_deploy_key` 路径，未读/复制/打印钥匙。每份脚本发送前断言不含CR，以UTF-8/LF **bytes** stdin传输，无text模式；逐步脚本sha256/exit/时间在 `private/fr-stage-r48-e578-20261027/*.json` 与同名log。原16:27失败原件另目录保留，没有覆盖。只新增首发stage目录/新副本及演练恢复库/角色/新unit；原 `zhiming_core_stage` 只读，live/Hermes未操作，未删除库/备份/旧unit、未杀PG会话、未修改认证/网络。新unit配置打印了loopback和cgroup阻断设置，但实际阻断正负验未执行，不能用配置代验收。

同SHA重复push CI40217250546于17:28只读核completed/cancelled，非failure；PR24成功依据保持原40217280728。实际模型调用0、应用外发0（依赖下载/公开交付传输不冒称外部网络0）。记忆41完整门及CI继续原轮，不受本次stage停止影响。首发stage未成功，31号生产未执行。
