# 主线集成只读核对（命理线）

核对轮次：2026-10-21北京时间10:39之后，本轮命理线续作；仅GitHub连接器读取。
首尾两次分支读取均为 `v4/integration @ 6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68`。
比较基准为我方 `f4da1267b83c4d3f65e80c5db59fce41848e2f3e` 的五份契约。
这是固定提交的事实，后续主线可能继续变化；未向主线聊天发消息或改其文件。

## 实际集成状态

目录查询成功列出 `docs/v4/release/integration/2026-10-21_P1b.md`，该目录无其他文件；
已完整读取的回执未提出P8专项反馈。其旧Charts套件数字不能当作本分支P8验收。
完整递归Git tree返回 `truncated=false`，该提交没有 `docs/v4/contracts/`，charts下仅
README、`__init__`、adapter及worker。因而该固定树尚未纳入本线显式P8模块；
此结论来自成功的目录和完整树读取，不由之前单路径404推断。

| 接线点 | 固定树事实 | 待主线处理 |
| --- | --- | --- |
| 主盘 | consultation仍调旧ChartAdapter.calculate并消费artifacts/claims | 显式新增P8路由，旧返回不能冒充chart_compute v1.1预览信封 |
| 时间口径 | charts README为地方平太阳时、八字sect2 | 新主解读走time_basis真太阳，北京差异并列；保留旧口径标签 |
| daily/window | 无对应新增模块或契约 | 按独立工具信封接线，保留快照、六用途、全区间排序和分页 |
| 黄历 | timekit.almanac接受带时区datetime，返回dataclass | P8接受严格日期、固定北京正午、返回c/r信封，不能仅按同名替换 |
| 合盘 | 尚无synastry接线 | 本次consent=user_confirmed先行；旧Fact的granted不自动等同本次同意 |

## 依据与边界

- [集成固定提交](https://github.com/JerryandShawn/zhiming/commit/6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68)
- [集成回执目录](https://github.com/JerryandShawn/zhiming/tree/6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68/docs/v4/release/integration)
- [旧consultation调用点](https://github.com/JerryandShawn/zhiming/blob/6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68/mingjing_core/application/consultation.py#L478)
- [旧Charts口径](https://github.com/JerryandShawn/zhiming/blob/6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68/mingjing_core/adapters/charts/README.md#L24)
- [同名黄历](https://github.com/JerryandShawn/zhiming/blob/6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68/mingjing_core/timekit/almanac.py#L42)
- [本线五契约基准](https://github.com/JerryandShawn/zhiming/tree/f4da1267b83c4d3f65e80c5db59fce41848e2f3e/docs/v4/contracts)

没有执行集成树或HTTP，没有持久化别名账本、真实授权/撤销、Agent/UI端到端证据。
当前结论为待接线，未发现已发生P8 API回归的证据。本线不因此合并任何分支；
继续本地只读计算和契约队列。PR#5保持草稿，项目服务器/真实模型/飞书请求0。
