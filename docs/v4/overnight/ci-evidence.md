# 夜间 CI 证据（2026-10-18）

本表按实际远端提交绑定，不把旧里程碑通过扩称为后续代码通过。只读取GitHub的状态与已完成日志；CI使用合成数据、回环PG15及空模型Key，不访问stage/生产或真实渠道。

| 工作线 | 已验证远端头 | 完整检查 | 已完成日志摘要 |
| --- | --- | --- | --- |
| P1 | `f4acf9e42185ef1a3e7d60cd4059872fbed14c84` | [Core 39045447795：success](https://github.com/JerryandShawn/zhiming/actions/runs/39045447795) | 旧Core553（1281.442s）；v4 339（87.50s）；自检48；端口89；覆盖619/656=94.36%；v1及c2脚本均80/80 |
| P2 | `cc1187e95f3f292c56985c99dac859420af63fcb`（本机等价树`de082ce1e6af37a706eee6a4596b09d1b6ca49e3`） | [Core 39051908909：success](https://github.com/JerryandShawn/zhiming/actions/runs/39051908909) | Linux旧Core553（877.930s）；v4 379（139.35s，零跳过）；脚本80/80、自检48（16.90s）。本机对应553（826.169s）与379（159.87s）亦通过 |
| P10 M1/M2 | `2d3863522b3f6a48130a492ceb2b77b63a4027e3` | [Core 39049929261：success](https://github.com/JerryandShawn/zhiming/actions/runs/39049929261)；[前端 39049929275：success](https://github.com/JerryandShawn/zhiming/actions/runs/39049929275) | 旧Core553（714.868s）；v4原250（54.45s）；脚本80/80、自检48；前端20单元、70浏览器（1.2m） |
| P8 计算子范围 | `f23b942ce698a3f7ee0b98c918d43053fe773433` | [Core 39048752187：success](https://github.com/JerryandShawn/zhiming/actions/runs/39048752187) | 旧Core553（692.439s）；v4 272（59.61s）；脚本80/80、自检48 |

P1覆盖率日志显示四舍五入94%，619/656的原始比值为94.359756%。P10的250是此独立分支保留的P0 v4测试，不是漏跑其他尚未合入工作线的新测试。四分支没有合成为一个经过验收的版本。

本汇总、回执和本文件属于随后追加的证据文档；它们的最新提交及检查见各PR Checks。代码验证和仅文档提交分别追踪，不以一次测试外推其它代码树、真实模型能力、真机视觉或线上效果。

P2曾发布的中间实现若检查失败，保留其历史，不重跑旧失败头冒充最终通过。最终修复树已实际通过；后续仅文档头`2afd389`的[独立检查39052747144](https://github.com/JerryandShawn/zhiming/actions/runs/39052747144)在本表编写时仍运行，不将代码检查扩称为该文档头检查。
