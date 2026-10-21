# B1 磁盘选择：明天决定，今晚仅离线准备

2026-10-18。用户已裁定 B1 固定 b9a89b6，tzdata 修复随 B2；本文件不改变发布输入。容量由用户明天选择扩容或整理。今晚没有 SSH、stage/生产访问、控制台操作、删除、搬移、快照或备份。现状只取 A 的安全摘要 `docs/v4/evidence/B1/2026-10-18-readonly-inventory.json`，不能把外部文档的示例设备名当本机事实。

## 可选路径与当前 No-Go

| 选择 | 可以解决什么 | 代价与边界 |
| --- | --- | --- |
| 优先扩容根云盘 | 为新包、双环境、安装峰值、dump/恢复副本、WAL/索引与后续增长留空间 | 控制台费用与可能重启需用户批准；云盘扩大后仍须按实际分区/文件系统扩展。不能据本次 A 判断设备名、文件系统、LVM 或在线扩容能力 |
| 逐项整理 | 释放已经确认无保留价值的特定文件 | 先只读列清精确目录、归属、最后使用、运行/回滚/证据依赖和释放量，再审写操作；不能直接对整个 cache/log/release/backup 根目录递归删除 |
| 先整理再扩容 | 在快满时为工具和运维留临时余量，再取得长期容量 | 两项授权分别审。临时空间不等于 B1 安装/恢复预算已满足 |

根分区最后观察：总 42,881,495,040 B，可用 791,592,960 B（约0.737 GiB）；当前不开始 prepare、dump、恢复副本或索引迁移。8 GiB 可用只是保守工程目标，不是测得最低容量；需先测固定包/双环境与恢复峰值，再审预算。新增增量控制器以至少8 GiB作为本轮失效关闭的保守门，若测量后要调低，须重审策略和控制器哈希。

| 路径 | A 已知计量 | 能否直接删 | 先核事项 / 风险 |
| --- | --- | --- | --- |
| `/root/zhiming-core-releases` | 未知；25秒限时计量未成功 | 不能 | 正在运行7dbc、Hermes wrapper、Charts解释器、回滚候选、证据引用均可能依赖；不能估算可释放量 |
| `/root/zhiming-core-backups` | 369,036 KiB，约360.4 MiB；12项 | 不能 | 只看元数据未验可恢复性；最近dump563,747 B、撤销15,221 B也不是本次最新备份。先定保留策略和异地/替代恢复证据 |
| `/root/.cache` | 1,314,504 KiB，约1.254 GiB | 不整目录删 | 分辨包缓存、下载、活动安装、应用状态及离线重装依赖；逐子目录证明可重建/未使用。此计量不代表全部可释放 |
| `/var/log` | 3,793,208 KiB，约3.618 GiB | 不整目录删/清空 | 区分journald、轮转日志和活动文件；保留故障/安全证据，审保留期和正规轮转。删除仍被进程打开的文件可能不立即释放空间 |
| `/var/lib/pgsql` | 101,296 KiB，约98.9 MiB | 绝不能 | PostgreSQL唯一权威、WAL/表空间不得手工删改；目录量也不是整个运行峰值预算 |

## 若选择腾讯云扩容：未来受审步骤

先核正确实例和云盘ID、快照/一致备份方案、回滚与维护窗口，不在本轮登录控制台或创建资源。控制台由用户选择目标实例对应云盘，调整容量并确认费用；云盘只支持扩大，扩大后还需让操作系统使用新增容量。[腾讯云官方扩容指引](https://cloud.tencent.com/document/product/362/5747)

获准服务器操作后先只读判型，记录输出并由操作人填写设备与分区变量：

    findmnt -no SOURCE,FSTYPE,OPTIONS /
    lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,PKNAME
    df -hT /
    df -i /
    ls -l /dev/disk/by-id
    sudo fdisk -l

以上当前都未执行。设备名、分区号、MBR/GPT、ext4/XFS、LVM/加密/RAID、多层映射仍未知；不能照抄 `/dev/vda 1`。存在LVM/加密/非末尾分区/MBR容量边界时停止，另出拓扑专用操作单；本文件不提供盲目重建分区或格式化命令。

确认云盘扩大、目标是可扩展的普通末尾分区且工具已就绪后，先执行 growpart 的预演，再审实际变更。以下变量是待填写的非密钥参数，空值不能执行：

    growpart -N "$REVIEWED_DISK" "$REVIEWED_PARTITION_NUMBER"
    sudo growpart "$REVIEWED_DISK" "$REVIEWED_PARTITION_NUMBER"

growpart 调整分区边界；它不代替文件系统扩展。若是裸设备上已有文件系统，跳过分区步骤。工具安装也是写操作，空间不足或需要重启时保持 No-Go，不能顺手重启生产。[腾讯云 Linux 步骤](https://intl.cloud.tencent.com/zh/document/product/362/39999)、[Canonical growpart 源码/参数](https://github.com/canonical/cloud-utils/blob/main/bin/growpart)

按已核实的文件系统仅选择一条：ext4使用对应设备/分区的 `resize2fs`；XFS对已挂载文件系统使用挂载点，不把两个命令都跑一遍。不得对已挂载根文件系统盲跑修复/缩容；工具提示异常时另审离线维护。

    sudo resize2fs "$REVIEWED_EXT4_DEVICE"
    sudo xfs_growfs -d "$REVIEWED_XFS_MOUNTPOINT"

上游说明 resize2fs 调整 ext 文件系统而不调整分区；XFS grow 工具要求文件系统已挂载。参数和在线条件以实际安装版本再核。[e2fsprogs 官方手册源码](https://github.com/tytso/e2fsprogs/blob/master/resize/resize2fs.8.in)、[xfsprogs 手册](https://man7.org/linux/man-pages/man8/xfs_growfs.8.html)

最后核 `lsblk`、`findmnt`、`df -hT`、`df -i` 的新容量/挂载/文件系统，检查数据和获准业务健康，记录实际耗时与剩余空间。若 cloud-init 已自动完成扩展，先核结果，不重复猜测执行。快照回滚也会影响新增合法写入和最新撤销/收据，不能当无损撤销扩容。

## 核验范围

官方资料于本轮离线准备时浏览：腾讯云控制台页面更新2026-05-18，Linux页面更新2026-08-04；同时查上游 growpart/resize2fs/XFS 工具文档。未取得当前云盘价格、设备拓扑、控制台在线能力或新服务器容量证据。扩容、整理和 B1 执行均保持未授权/未执行，等待明天决定。
