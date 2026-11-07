# 合并候选 stage 回执：afdfc99790984105

- 候选：`6d803bff9832f2a9582c09d25e0a6b9c6207dddc`；stage operation：`afdfc99790984105`。
- 包 SHA256：`7b72e68d10ad281a67cd87f0574974d40408b045e324125bd8e39a7da50ac012`；bootstrap SHA256：`18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42`。
- 同源 Core CI 42337532390、时区 CI 42337532311 均 success；R11 首发门 48/48、7/7、69/69、29/29、X02 通过，真实请求 0。
- 本机分片：非 release 4510 项全过；release 627 项覆盖完整，原始 3 个分片失败在标准 narrow runner 复核通过。
- 本机 37 号、交付哈希、K3 文件和远程只读预检通过。新 release 解包、独立 venv、Core 锁安装、pip check、K3 核验成功。
- 旧 stage root/unit/库未删除。旧库和 writer 分别改名保留为 `zhiming_core_fr_stage_e578e2d` 与 `zhiming_core_fr_stage_e578e2d_writer`；本次 operation、unit 和 writer 均为新对象。
- copy、prepare、投影核验、空增量备份、恢复、seal/exchange 与回滚证据均 exit 0。
- 新 unit `zhiming-core-fr-stage-afdfc99790984105.service` 通过 systemd 校验并实际 active；健康/状态/历史均 200，实际 cgroup 出站阻断、writer 负验和维护 503 均通过。
- 最终仅新 unit 停止并 capture+seal，最终 inactive；维护门保留。实际模型请求、飞书外发均为 0。生产尚未开门。
- 私有脚本、每步日志和回执位于 `private/stage-afdfc99790984105/`。早期目录/拼接/布局失败均保留，未覆盖后冒充一次成功。
