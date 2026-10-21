# P3 离线首切片验证（2026-10-18）

代码本机97f656c / 远端e9ad78b，P1/P2合并基底b9a89b6。

真实PG目标63/63（73.30s）、全v4 678/678（208.35s、零跳过）、旧80脚本与48自检均通过。命令、原始日志SHA及范围见offline-validation-2026-10-18.json；源文件指纹见validation-summary.json。R07 300轮和10000消息使用真实MemoryService/PG，原消息哈希不变、远处3约束保留、超预算压缩与拒绝都经过同一ContextEngine。所有外部模型请求0。

Ruff E/F/I/B/UP/SIM、format120与AST大小限制通过。独立review发现混epoch工具配对会丢reasoning，已补同一非空tag校验；重复遮盖、后到消息注入、目录截断及摘要回执丢失均有反例回归。原始失败复现留task，未删改成通过证据。

计量是policy_units，actual/upper_bound token均null；会员token硬门、运行时、中央账本/guard、持续提醒未接线。完整P3及F1/P5b B尚未完成。旧Core在本P3未重跑，P2已有553基底证据；最终CI待发布草稿后核验，不把初始计划提交的CI当新代码CI。
