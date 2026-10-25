# 首发 stage 回执：已停止，未执行远端命令

候选：`e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd`；operation：`4e680f175ea28cc8`。37号Go已在SSH前读取并核验，成功PR CI run40217280728；Go及执行单hash见 `../eval/v50_stage_stop.json`。

实际首次SSH：北京时间03:04:14.999–03:04:25.052，exit255，`Connection timed out during banner exchange` / `Connection to 1.14.59.242 port 22 timed out`。尚未认证或进入远端bash；按v50/37非预设异常停止，不改SSH、网络、权限或认证，不扩大“连接拒绝”重试例外。自动推进已暂停，等待直接人类恢复。

|项目|exit|结果|
|---|---|---|
|本机Go/候选/包/分词器核验|0|成功|
|SSH只读前置核验|255|失败：banner exchange timeout|
|备份|—|未执行|
|复制|—|未执行|
|迁移1–8|—|未执行|
|回填第二次0变化|—|未执行|
|撤销重放|—|未执行|
|空增量恢复与改名对调|—|未执行|
|服务启动|—|未执行|
|无模型冒烟|—|未执行|
|出站阻断正负验|—|未执行|
|writer负验|—|未执行|
|维护门503|—|未执行|
|收尾inactive/closed|—|未执行|

SSH尝试1；上传0；远端修改0；真实模型0；外发消息0。原stage/live/Hermes/服务没有被本次操作改动；因SSH不可用，不能宣称实际健康状态已经复核。未创建R28管理员/DSN文件或新unit，未切库、未启动服务、未进入生产；无本次远端改动可回滚。inactive/closed状态未验证，不补造成功回执。

重复push CI run40217250546于03:05:28仍in_progress/null；未cancel/rerun，不用它代替已成功的PR CI。恢复前须再核37附加规则。原始本机记录：`C:/Users/Administrator/Documents/Codex/zhiming-v4-r46/private/stage-4e680f175ea28cc8/preflight.json`。安全索引：`../eval/v50_stage_stop.json`。
