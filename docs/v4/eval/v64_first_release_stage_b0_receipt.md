# 首发stage B0停止回执（2026-10-27 16:27 北京）

候选e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd，operation4e680f175ea28cc8。37号首行Go/复核时间2026-10-26 03:05/同SHA CI引用已核；冻结树clean、原tar/bootstrap SHA256及delivery身份、公开tokenizer六文件verify-only均通过，没有重建或覆盖首发包。

| 项目 | 实际结果 |
|---|---|
| R45 SSH显式密钥路径探测 | exit0，root@1.14.59.242认证成功；未读取/复制/输出钥匙内容 |
| B0 已审脚本首次发送 | exit2，远端首行错误`bash: line 1: set: pipefail\r: invalid option name` |
| 目录/数据库/上传/副本/服务 | 未进入；首行解析失败，未执行这些步骤 |
| B1–B8 | 未验证，不能填写成功或首发stage完成 |
| 真实模型/应用层外发 | 0 |

原因是本机Python subprocess文本stdin在Windows上将LF转成CRLF；这是主线传输处理错误，不是服务器前置条件不满足。原始回执和日志保留DEV/private/fr-stage-e578-live-20261027/b0.json、b0.log，原脚本亦保留。已仅在本机准备b0-reviewed-lf.sh原始UTF-8/LF字节文件并断言无CR；没有再次发送/执行，没有现场修补服务器或重试。

按执行单“任何非预设负验异常：立刻停，保持当前库/门/文件；不修补重试”停止stage；后续继续须大脑对这次传输偏差给出指令。原stage/live/Hermes、数据库、备份和unit未改；不宣称Linux完整验收/生产上线。记忆候选本机测试独立继续。
