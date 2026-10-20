# B1 本机 Linux 演练：环境阻塞（No-Go）

记录基准：2026-10-20 22:48–22:54，北京时间（Asia/Shanghai，+08:00）。本机系统时区不用于验收。

本轮没有可用的 Linux PG 15 容器，不能宣称备份、恢复、Linux 权限、跨 exec writer fence 或 Native 控制器通过。B1 发布候选仍固定 b9a89b6；0008 仅属另外的本地兼容用例，不进入 B1 包或 stage 授权 0005–0007。

## 实际尝试与结果

1. 只读探测：Docker Client 29.5.2，context desktop-linux；daemon 尚未运行，命名管道 dockerDesktopLinuxEngine 起初不存在。WSL2 的 docker-desktop 和 salad-enterprise-linux 均为 Stopped；没有取得镜像清单，没有拉取镜像。
2. 按主线批准隐藏启动既有 Docker Desktop。客户端 info/version 挂起；本机 backend 日志报告 Inference manager 监听用户 LocalAppData/Docker/run/dockerInference 时失败，旧 socket 不能访问，错误为 filename/directory syntax incorrect。没有使用 Reset to factory defaults。
3. 独立现有 WSL fallback 仅尝试执行 uname/查找程序，salad-enterprise-linux 在挂载其既有 ext4.vhdx 时返回 Wsl/Service/CreateInstance/MountDisk/HCS/E_ACCESSDENIED；未进入 Linux shell，没有改挂载或权限。
4. 经主线明确批准，仅复核并停止本轮启动的 Desktop/backend 精确 PIDs 37420、15772、37512（路径在 Program Files/Docker/Docker 下），先前只读 CLI PIDs 17700、39792 也已停止。确认 dockerInference 是 0 字节、属性1056的临时 reparse 项；尝试将该单项重命名为带北京时间的 backup。普通 LiteralPath 与扩展绝对 LiteralPath 均返回“系统无法访问此文件”。重命名未发生，原项保留；因失败没有再次启动 Desktop。

## 保护与后续

未删除文件、目录、容器、volume、数据库或备份；未 reset；未改全局权限；未执行 wsl --shutdown；未停止其他 PostgreSQL 或服务；未访问 SSH/stage/live；未调用模型或飞书。没有创建演练容器/volume，也没有生成 restore proof。

环境修复尝试已经停止，避免循环重试。继续交付固定本地资源与真实 PG 命令的可重复脚本和替身传输契约测试。此类纯测试及可能的 Windows PG 对照都不能冒充 Linux 容器演练。待可用 Linux runtime 恢复后，必须补真实 PG 15 backup→restore→迁移→权限→rollback 的证据，再审 Go；现为 No-Go。
