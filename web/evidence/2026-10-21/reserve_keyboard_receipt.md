# P10 储备c：完整键盘流程与焦点修复阶段回执

- 分支：v4/p10-frontend；本回执随修复提交；PR https://github.com/JerryandShawn/zhiming/pull/6 保持Draft。
- ExecPlan：web/ExecPlan_week_2026-10-21.md。

## 完成了什么

- [x] 接受/拒绝片段后原控件移树或disabled：只修复已丢失焦点，新片段可聚焦，目标折叠回页标题。用户曾转去其他控件即取消恢复意图，不抢焦。
- [x] 手动继续队列在claim前捕获焦点，复用原受保护composer回焦；不改草稿、FIFO、停止手动继续或未ack保护。
- [x] 原8条手机/桌面全键盘流程：嵌套选择器/原话、应用和字段撤销双确认、流式插话停止取消继续、月历/依据Sheet/设置往返；8/8最终通过，8截图。

## 评测分数

新增11/11单测，连同旧整理/队列/v1会话兼容合计38/38；8/8浏览器，类型/lint零警告/构建通过，Axe全规则0/朱砂≤3/API与外域0/控制台0。初轮原8项1通过/2真实失焦/5未跑，未删除或放宽原断言。新增unit初轮10/11的1失败是jsdom disabled.blur不生效，显式body焦点模拟浏览器fallback后原恢复断言通过。所有首轮摘要/报告SHA保留于reserve_keyboard_checks.json。

## 关键文件

web/src/organize/OrganizeReviewPage.tsx、ReviewTree.tsx、web/src/night/useNormalConversation.ts；新增11单测和8流程E2E。

## 数据库迁移与回滚

无迁移、真实资料修改或投递；回滚本前端提交后重建。

## 偏离设计 / 未验证 / 风险

模拟端口执行，真实模型0；无服务器、飞书、合并。回焦修复不写业务状态，不新存确认票据。此头完整回归/全站矩阵/冷4G仍另验，不能沿用旧数字；储备b其余状态和d文档边界仍继续。

## 需要用户或大脑决定 / 下一步

无需等待回复。先推送当前源，冻结后测当前头性能；08:30–45启动完整回归。白天命理研习真实212术语/39来源及学习卡已只读定位，接线缺口与路径在ignored study-source-notes.md，后续接入而非覆盖个人符号词典。
