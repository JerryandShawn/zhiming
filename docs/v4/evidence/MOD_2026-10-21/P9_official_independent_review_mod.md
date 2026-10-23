# P9 官方 v3 独立复核（模块线）

日期：2026-10-21，北京时间。只读审阅产品与指南，只新增独立测试及本说明。

依据为大脑交付目录26号全文317行、57048字节，SHA256为
`70883c7517e7796039e5481c8d41fa5ca7d499da3b210a65a40ed3657f2318bb`。
先冻结184条规范矩阵，再写公开API验收；矩阵SHA256保持
`2fca0ce9b79c45a80106544e85de49c5d95f8a19a9f2317797578b61deec10bb`。
184条是规范条目数量，不是已执行的184项平台测试。

## 最终本地结果

- 新增builder边界测试46项通过；与此前独立wire/state 84项合跑，**130 passed / 0.83s**。
- wire/state测试内另有1000组固定种子SHA256派生与实际int32样本。
- 最终测试在core声明最终冻结后执行；未改原184条期望、原84项文件、旧卡片或Q6测试。
- 测试全为本地合成数据。真实模型、网络、飞书、服务器、数据库和Git操作均为0。
- 02至07时段存在额度中断，不作为持续开发或持续监测证据。

新增文件为`tests/v4/p9_official_v3/test_acceptance_builders_extra_mod.py`。
首次试跑的长文本参数未指定短ID，触发Windows测试临时路径问题；补短ID后原样文本通过，未缩小测试数据。

## 发现与修复归属

源码审阅发现`answer_card`按1500字阈值提前截成1200字，尚未达到字节预算也丢全文。
root确认并修复新增产品：先保留完整回答、依据，仅实际超预算才缩短可选正文。
独立测试固定1601个英文字符、8000个汉字及超过1200字的依据，最终均完整保留。
这项问题在独立断言第一次可运行前已由root修复，不冒称有一份修复前失败报告。

指南最初缺具体scope、`header.event_id`与`event.action.value.t`、平台不补推、实体回调toast-only，
富文本链接也未使用26号的v2路径。root修复产品注释与指南；独立测试核对最终链接、权限和字段。
本子任务没有修改产品或主线指南。

## 对照26号第8节

| 项 | 独立复核与验证边界 |
| --- | --- |
| 1 双步骤关闭 | finalize/close_streaming分别请求、operation/UUID/seq/ACK；双ACK才closed。每步拒绝、重试、unknown、恢复及对账有目标测试。 |
| 2 wire UUID | 以完整UTF8 operation_id计算SHA256前40位；固定及1000组合成样本、恢复不换UUID。 |
| 3 空文本 | offer/reset空为noop_empty，不分配seq、不发PUT，也不声称远端旧文已清空。 |
| 4 标识符 | element_id官方正则及1/20边界；card_id 1/20长度与非法边界。 |
| 5 sequence | 真正int32，拒bool/浮点/字符串；单卡统一递增。跳号仍是stage未知，配置不构成官方证明。 |
| 6 错误映射 | 全部列出的码、5xx、网络与未知码；429/reset按秒；200850/300309交host决策，不新卡。 |
| 7 字面转义 | 原冻结实体映射、question/why/selected、receipt、proposal、route。plain_text按钮原文保持。 |
| 8 体积 | 真实UTF8内卡与嵌套finalize wire分开量；反斜杠二次膨胀；200个body组件树边界；超限保留回执与动作。 |
| 9 update_multi | 七类新builder及占位采用显式true；结构检查不是平台发送验收。 |
| 10 接线 | 指南已说明路由/权限/回调三token与3秒HTTP200要求；durable命令、SDK和真实时限均未接线。 |
| 11 主线提示 | 发送错误分类和tenant token缓存只写接线说明；没有修改旧feishu.py或读取token。 |

builder额外验证了九类回执状态不晋升为成功；超预算强制回执拒绝而非静默移除；
提案三动作、归区两动作、敏感跟进预览与回复动作保留；七区大晨报标明缩略并保留链接。
预算使用28000/30000十进制字节的工程保守口径，不声称官方“30KB”的精确单位已实测。
Markdown正文须来自可信host产物；构建器不是正文权限、来源确认或写入授权服务。

## 官方索引（转录26号，不是本子任务联网复核）

- [JSON 2.0结构](https://open.feishu.cn/document/feishu-cards/card-json-v2-structure)（2025-06-23）：第4/8/9项。
- [v2富文本](https://open.feishu.cn/document/feishu-cards/card-json-v2-components/content-components/rich-text)（2026-08-27）：第7项。
- [全量更新](https://open.feishu.cn/document/cardkit-v1/card/update)（2025-07-03）、[更新设置](https://open.feishu.cn/document/cardkit-v1/card/settings)（2025-08-05）：第1项。
- [流式文本](https://open.feishu.cn/document/cardkit-v1/card-element/content)（2025-08-22）：第2至6项。
- [创建实体](https://open.feishu.cn/document/cardkit-v1/card/create)（2025-07-03）：第10项。
- [发送消息](https://open.feishu.cn/document/server-docs/im-v1/message/create)（2026-04-10）：第2/8/10/11项。
- [普通卡更新](https://open.feishu.cn/document/server-docs/im-v1/message-card/patch)（2025-07-15）：第9/10项。
- [回调](https://open.feishu.cn/document/feishu-cards/card-callback-communication)（2026-05-09）、[延时更新](https://open.feishu.cn/document/server-docs/im-v1/message-card/delay-update-message-card)（2025-09-10）：第10项。
- [tenant token](https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal)（2026-10-14）：第11项。

## 原10项未知均保留

1. seq跳号能否被平台接受。
2. 单次完整卡JSON将streaming置false是否独自关闭流。
3. 初始markdown空内容是否被平台接受。
4. `&`及工程额外的`|`实体如何实际渲染。
5. 实体回调card.raw与CardKit seq如何相互作用。
6. CardKit UUID去重窗口时长。
7. open_id字符集及长度。
8. reply是否支持卡片实体。
9. 真机锁屏/系统推送究竟显示什么，不能用summary配置代替真机证明。
10. 同卡流式10QPS与“不触接口限流”的官方文档冲突。

另有30KB精确单位、首条私聊前置条件、延迟更新控制台scope映射三个补充未验证项。
这13项继续标`unverified_stage`；本地替身、代码注释和文档链接均不能消除这些未知。
真实PG租约/事务、持久化命令、SDK回调、网络错误恢复、设备显示和实际飞书投递仍需主线另行授权接线。
