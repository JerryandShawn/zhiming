# 合并候选 stage 回执：bcac4df7780c4516

- 候选：`bf6e0bbc720b85510d757b17d4ccd74ff60687bb`；stage operation：`bcac4df7780c4516`；执行单 release-prep `75291f83`。执行时间 2026-11-08 02:44–03:12 UTC（北京时间 10:44–11:12），B6 完成后 02:51–03:11 UTC 间因本机网络中断暂停，恢复前只读核实无半截块。
- 包 SHA256：`3294003e56ca152b6de7f1127e68f850e25f4eb114b5b7478b1f810a7f46d59d`；bootstrap SHA256：`18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42`；delivery 1863 个跟踪文件。
- 37 号（首行 Go、复核时间 2026-11-08 02:36 +08:00）、同源 Core CI 42388565834 success、R11 48/48、7/7、69/69、29/29、X02 通过。本机 37 号门、候选 clean/HEAD、包与引导 hash、K3 原件、delivery 身份全部通过（两次：连接前与上传前）。
- B0.5：清理前根分区可用 9,216,536 KiB，pip/dnf/npm 缓存清理后 9,216,520 KiB（无可观回收；pnpm store 不存在）。B1 8GiB 门通过（9,216,576 KiB），PG15 程序 hash 已记录，新 root 子目录/unit 均为全新。
- 上传三份交付物与六个 K3 公开文件 exit 0；服务器两 hash 复核一致，新 release 解包（`unpacked_new_release`，service_started=false）。venv（`venvs/<sha>/core`）与 Core 锁依赖后台完成 exit 0；pip check 无问题，服务器 K3 revision f831ab66… 6 文件核验通过。
- R28：本机回环管理员认证通过，两份私有文件 600/root，凭据输出 0。
- B2.5：两个旧 unit inactive/MainPID=0、8788 无监听；旧库 OID 70807 改名为 `zhiming_core_fr_stage_6d803bff`（closed），旧 writer OID 72548 改名为 `zhiming_core_fr_stage_6d803bff_writer`；终止会话 0、删除对象 0，回执 `stage-6d803bff-preserved.json`（`B25_RENAMED`）。
- B3–B5：copy（源 `zhiming_core_stage` OID 24580 → 目标 OID 74283）`copied_closed`；prepare `prepared_closed`，迁移 1–8 checksum 匹配，backfill_repeat 全 0，replay_full_state_unchanged=true，模型/外发 0。
- B7：capture、空增量备份 `backed_up_closed`、新库恢复 `restored_new_database`（74283 → 77182）、seal `closed_zero_connections`、exchange `exchanged_closed`：current_oid 77182，failed 库 `zhiming_core_fr_bcac4df7780c4516_failed`（74283），admission_opened/old_database_deleted/production 均 false。
- B6：provision `provisioned_closed`（新 writer `zhiming_core_fr_stage_writer` OID 78895，DB OID 77182）；systemd-analyze verify exit 0，输出仅为豁免行（原样）：`/etc/systemd/system/tat_agent.service:7` PIDFile /var/run；`/usr/lib/systemd/system/ip6tables.service:14`、`:15` 与 `iptables.service:14`、`:15` Standard output type syslog is obsolete。unit 安装 hash 一致，admit `copy_database_admitted`，`zhiming-core-fr-stage-bcac4df7780c4516.service` active（MainPID 436600，NRestarts 0），IPAddressDeny=0.0.0.0/0 ::/0、Allow 仅回环、SocketBindAllow=ipv4:tcp8788、仅 127.0.0.1:8788 由新进程监听。
- B8：health/state/history 均 200（health model=stage-model-access-disabled）；实际新 unit cgroup 出站阻断通过（主机可达 223.5.5.5:443，cgroup 内被拒，应用 payload 0）；writer 负验得到预设 `INCREMENTAL_FILE_FENCE_BUSY`；维护门建立后三端点均 503。
- 收尾：仅停新 unit，最终 inactive（Result=success，8788 无监听）；finish capture + seal `closed_zero_connections`（OID 77182）。新副本与 failed 库均 datallowconn=false、0 连接，维护门 `maintenance.json` 保留。实际模型请求、飞书外发均为 0。
- 原 `zhiming_core_stage`/`zhiming_core_live`、mingjingtai/飞书/报告/Hermes 未改动、未启停；未做任何生产步骤。收尾后根分区可用 8,447,684 KiB（新 venv 约 546 MB、release 约 22 MB、operation 约 6 MB）。生产尚未开门。
- 每块脚本（UTF-8/LF/无 BOM 原样摘取，公共头拼接）、日志、exit 记录与只读核查位于 `private/stage-bcac4df7780c4516/`，驱动 `private/stage_remote_bcac4df7780c4516.py`。本次无失败重试块。
