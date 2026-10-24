# P3 与 integration 的普通合并候选：尚未接收

记录：2026-10-21 11:14 +08:00，北京时间。用户33号允许在integration子分支准备组合，正式`v4/integration`本次仍保持`6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68`；没有向该分支、`v4/main`或`main`合入任何P3提交，没有部署。

## 精确图与可复核范围

- 子分支：`v4/p3-wire-integration-20261021`，复用主线独占的integration工作树；不重建、不reset旧分支。
- base：`6e47a058f389bd8b6bf82c0f55fca3b3c4e6aa68`，已接P1b及后续回执。
- source：P1b/P3组合Draft PR #13的`c0892a40a8a91630f82a8a61bb7c989c02e2129c`。
- 真实普通merge：`6841237956bca05985fd90653bf1d13088b9f600`；两个父按上述base、source顺序保存；tree `d787c75e321662ea88b64ae543fd9d9a986488dc`。
- 合并前`merge-tree`只读预演与真实tree相同，无冲突。相对source仅两份既有integration回执/计划有差异；`mingjing_core/tools/config/charts/static/tests/.github`逐路径Git diff为0，因此未在此再实现第二套P1b守卫。

根独立核原`b9a89b6f84f7bebb640de080548010859aae630c`七份0001–0007迁移Git blob与本候选逐一相等。0008仍归P1b，0009预留P5b；本分支不改B1包，也不把0008装入B1授权。

## 测试与放行判定

本次做的是Git图、无冲突、代码树相等和历史迁移原字节核查，没有在11:15窗口末端抢跑第五条完整链。已有wire固定ff4的Core583、09点固定wire的v4与M8各自有原回执，但不能直接改写成本merge头测试成绩。source关联PR CI在11:00前仍运行；实际CI checkout必须另核，不能只凭关联head认领通过。

后续在合规窗口固定本分支提交，按33号要求跑Core、v4、Charts及既有web回归，记录命令、版本、开始/结束与原始产物hash。不得在当前三个在途主线宽验之外失控加并行。工作区中的P4 M4/保留/receipt候选也不混入本次P3树；P4/P6/模块/P8/前端仍独立。

原P3脚本46/47的X03四条网页/飞书发送边界断言、旧页面记忆回执DOM、受信实际encoder依赖及真实评测仍未收口。故本候选**不是P3验收，不是正式integration接收**。各源的旧失败/skip均保留。全部真实供应商请求、飞书发送和服务器访问为0；31无Go、30 No-Go以及B1 Linux/删除收据往返阻塞不受此Git候选影响。

## 回退与继续

仅新增自己的普通merge子分支；正式integration引用未移动，不需要reset/rebase/强推或数据回退。后续失败只在子分支留证修复，不带着未解释失败宣称整体可用。真实模型只能等待用户在线明确开始，stage/生产仍按用户条件授权，不由本候选解锁。
