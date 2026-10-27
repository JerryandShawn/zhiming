# 首发 stage 成功回执（37号 / main67 R49）

候选 `e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd`；operation `4e680f175ea28cc8`。R48实际17:27–17:33执行至启动；R49于18:07:48只读核现场一致后从停止点续行，**18:08:30北京时间完成**。原包/37号/成功PR24 CI40217280728不变；重复push40217250546只读仍cancelled，非failure。没有从B0再做。

|37号要求|exit / 实际结果|
|---|---|
|Go/clean/原包/分词器、B0与独立环境|0 / 固定原件匹配；LF bytes无CR；依赖锁及管理员验证过|
|备份、只读复制|0 / copied_closed；原stage只读|
|迁移1–8|0 / checksum全匹配|
|回填第二次、撤销重放|0 / 三项repeat均0；replay_full_state_unchanged=true|
|空增量备份/新库恢复/封闭/改名|0 / backed_up_closed、restored_new_database、exchanged_closed；旧库未删|
|服务启动、R49现场复核|0 / active；副本65685 admitted，旧副本62786保留且closed|
|健康/状态/历史无模型冒烟|0 / 三个GET均200，health模型拒绝标记核过|
|实际unit cgroup出站正负验|0 / 主机223.5.5.5:443正验通、相同地址在实际stage cgroup内拒；应用payload0|
|writer负验|0 / 原生INCREMENTAL_FILE_FENCE_BUSY，未获独占锁|
|维护门|0 / 三个GET均503|
|收尾和只读终验|0 / unit inactive/MainPID0，8788无监听；维护门保留；65685及62786均closed、连接0|

systemd verify原exit0，**仅按R49豁免以下原始行**；两执行单已加入逐行完整匹配过滤，任何其他警告仍停止，不改、重载或停用这些既有unit：

```text
/etc/systemd/system/tat_agent.service:7: PIDFile= references a path below legacy directory /var/run/, updating /var/run/tat_agent.pid → /run/tat_agent.pid; please update the unit file accordingly.
/usr/lib/systemd/system/ip6tables.service:14: Standard output type syslog is obsolete, automatically updating to journal. Please update your unit file, and consider removing the setting altogether.
/usr/lib/systemd/system/ip6tables.service:15: Standard output type syslog is obsolete, automatically updating to journal. Please update your unit file, and consider removing the setting altogether.
/usr/lib/systemd/system/iptables.service:14: Standard output type syslog is obsolete, automatically updating to journal. Please update your unit file, and consider removing the setting altogether.
/usr/lib/systemd/system/iptables.service:15: Standard output type syslog is obsolete, automatically updating to journal. Please update your unit file, and consider removing the setting altogether.
```

原件：`private/fr-stage-r48-e578-20261027/`逐脚本sh、sha256、exit/时间json/log及success-receipt.json；两次历史停止原件均保留。每个SSH/SCP显式现有密钥路径，脚本发前无CR断言、UTF8/LF bytes stdin。管理员/网站token/DB口令只远端私有文件，未打印/回传。未删除任何库/备份/unit、未杀PG会话、未改原stage/live/Hermes或认证网络。实际模型调用0、应用外发0；依赖下载与交付传输另计网络操作。只读终态核验后不再远端操作，**停下等31号；生产未执行，未宣布首发上线**。
