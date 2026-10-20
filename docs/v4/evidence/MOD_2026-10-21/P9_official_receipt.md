# MOD-P9 官方协议候选里程碑回执

- 分支：v4/mod-organize；此前builder checkpoint为7f8ee338a09aa03840decabcb7e9bdf57ee86236；本次最终提交由root发布后登记。PR：[10](https://github.com/JerryandShawn/zhiming/pull/10)，保持Draft。
- ExecPlan：docs/v4/execplans/MOD_P9_official_20261021.md。

## 完成了什么

- [x] 新增七类JSON2 builder与严格ID/seq/UUID、update_multi、非空占位、官方实体转义、200组件和完整请求预算；未超预算保全文，超限保留回执/操作。
- [x] 新增纯CardKit wire、双步骤finalize/close、独立seq/ACK、400ms节流、错误分类、明确拒绝/未知对账、严格恢复与reconciliation子树CAS。
- [x] prepare/claim/dispatch绑定实际wire与当前host产物；Q6来源/完整manifest/成功run/完整validation及未知不重发门禁保留。
- [x] 184条规范先冻结，独立130项实际API验收，含1000 SHA/int32样本；不是184个平台通过。
- [x] 全新P9目录346 passed/7.73s（core50、独立130、root builder63、旧守卫98、namespace重放5），包括两个阶段各1000组FrozenClock/失效来源路径。
- [x] 38个P9/评测材料Python源的Ruff、format、AST及基底只新增审计；基底既有文件变更0，详见P9_EVAL_source_boundary_audit.json。
- [ ] 本次新增P9的合法窗口全量回归待07:45开始；真实PG/SDK/HTTP/飞书与设备效果未接。

## 评测分数

上述346为本地合成程序测试，不是模型或平台质量分。实际模型调用0。没有修改或重跑旧v2.1/v2.2基线，没有再次开封Q5 B。旧P9/Q6入口保持冻结。

构建器最终性能：1000条大回答含真实typed回执/4动作，中位1.159378秒、Python峰708987字节；100条七区大晨报1.071426秒、峰7173439字节。完整inner/wire预算校验和断言计入；synthetic CPU，不是网络吞吐。P9_official_builders_performance_final.json绑定最终builder源；旧提前截断版本的报告另留历史，不能混作最终结果。状态机单独性能仍待补。

## 改了哪些关键文件

新增card_limits_official_v3.py、cards_official_v3/、cardkit_official_v3/；新tests/v4/p9_official_v3/与官方矩阵；新接线P9_official_20261021.md。所有为本轮新增入口，不改旧适配器。

## 数据库迁移与回滚方式

无迁移或真实效果。主线未opt-in，停用新入口即可回退候选。不得为回滚删除unknown意图、换business key重发或清空对账信息；实际PG/CAS/租约/fence必须由主线事务接线。

## 偏离设计的地方及理由

用户只新增优先于26号允许修改旧文件的建议：旧候选“待核实”注释原样保留，不能声称全树已清零。28K/30K为十进制字节工程余量，30KB官方精确单位未实测。空reset采用noop_empty，远端旧文不保证立即清空。

## 未验证 / 已知风险

13项平台未知见独立复核与接线指南。Webhook验签/身份、3秒HTTP200、平台不补推后的持久化命令、控制台scope、长连接、tenant token缓存、普通卡PATCH、锁屏、客户端及真实网络故障恢复均未实测。

当前流式final只支持带answer组件并可映射Core4 text的最终卡；非answer提问/提案/记忆回执映射受控拒绝。真正运行中草稿没有因这套completed-run门禁获得授权。自动reopen和查询平台最新seq未实现，交host决定/对账；10002关闭拒绝的重试只是一次描述，host须遵守永久错误分类。

独立审阅修复了无条件提前截断与文档缺口；root五阶段重放测试再修复dispatched相同metadata被错误判退步。曾有1/5实际失败与bare helper收集错误，原因/修复记ExecPlan，断言未降标。后续source hash以最终审计/合法窗口报告为准，代理修复前fe29摘要不代表最终。

## 需要用户或大脑决定的问题

上线前13项stage口径、非answer最终卡Core4映射、运行中草稿可信协议、远端高水位接线。记录待决，继续其他纯模块，不等离线用户，不自行访问stage。

## 建议后续

先在主线离线集成真实业务事务和显式故障替身，再按其单次授权处理平台验收。补状态机完整链性能、分支覆盖及非answer映射；本回执不能作为P9阶段Done证明。
