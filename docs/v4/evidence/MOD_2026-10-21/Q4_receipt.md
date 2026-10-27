# Q4 P7调度纯核心阶段回执
- 分支：v4/mod-organize；提交号见日报随后实际推送记录；PR：https://github.com/JerryandShawn/zhiming/pull/10（保持草稿）。
- ExecPlan：docs/v4/execplans/MOD_2026-10-21_continuation.md
## 完成了什么
- [x] 日/周/月/年/工作日/休息日/农历循环下次时间；P2只读调休，缺日skip，DST和未知安排澄清。
- [x] U4机器规则桥接不猜时刻；晨报订阅默认07:00，K1 quiet豁免。
- [x] K2明确提醒到点/迟到60分钟与12小时端点；顺延保留original_due，领取时完整重算。
- [x] 旧来源/静音/日限/接收度与预览规则保持，普通followup仍默认08:30恢复；没有重开使用时长提醒或登记紧急联系人。
- [x] 新指南、冻结独立矩阵、随机属性、性能与tracemalloc证据。
## 评测分数
- Q4共1240项本地验收；独立170项为子集，另有4000组规则/投递随机断言及200实际P2查询。
- 在本线45–60分窗口启动的全量已完成模块回归4369/4369，7.85秒；报告Q4_completed_modules_regression.json。
- Ruff/format/尺寸17个Python文件通过；120次混合循环计算中位0.595090秒/峰值38206字节，1000投递计划中位0.022787秒/峰值5999字节。
- 真实模型、服务器、飞书请求0，无模型下载。未验证生产定时或真实通知时延。
## 改了哪些关键文件
新增scheduling/、tests/v4/scheduling/、benchmark_scheduling.py；指南docs/v4/integration/mod/Q4_scheduling_20261021.md。
## 数据库迁移与回滚方式
无迁移或运行入口修改。纯计划不保存已发送ID、不取得PG租约或扣额度；主线通过既有事务/Outbox接线。停用新增候选引用即可回退。
## 偏离设计的地方
K2对用户自定义quiet_end先保守继承用户设置，默认精确08:00；28未明确此分支，已列待决。普通followup保持旧08:30。无法确认的循环时刻/日历安排不自动排程。
## 未验证 / 已知风险
并发领取、原子日计数、真实租约/Outbox/重启、系统锁屏投递和飞书均未验证；旧allowed不是永久许可，发送前必须recheck。继承的规则不代表D4 usage触发器已存在或被开启。CI需按对应提交实际状态单列。
## 需要用户或大脑决定的问题
自定义quiet_end的K2最终口径：当前遵守用户设置；默认08测试已达裁定。不等离线用户，继续下一队列。
## 建议后续
主线持久化稳定occurrence/original_due/subscription revision并接原子claim；模块线继续整理v2，冻结B231不参与调参。
