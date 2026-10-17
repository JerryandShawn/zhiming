# 夜间独立复核与修复记录

本记录汇总跨工作线只读复核及实际修复，不替代阶段回执。复核者没有连接PG、运行迁移、调用模型或修改被审计实现；PG验证由各实现线/主代理在本机隔离库完成。

## P1：协议、重试和错误边界

独立复现发现并修复六类边界：退避超过总截止时间后仍发请求、上一用户轮的reasoning被回传、JSON指数溢出、Anthropic多Part工具结果编码、不可读429响应体被误分类，以及供应商链未共享逻辑总截止时间。取消关闭连接的竞争另经复现检查。对应MockTransport回归通过，最终端口89、完整v4 339通过；CI绑定见`ci-evidence.md`。

## P2：来源、撤销、历史和时刻生命周期

- fact-only撤销原先只脱敏助手，未把助手ID继续传到note/profile等新派生层。修成typed多跳闭包，含origin run/outbox反向污染、旧legacy助手分支和删除重放。独立逆序依赖探针与实现线真实PG定向均有证据。
- Feishu源ID和operation_id格式不同，原回填fallback又来自set顺序。修成精确request source ID优先、核对owner/subject/role/原话；歧义或损坏记录跳过，不猜渠道。
- 旧助手回填的created_at是插入时间，先按其截前10000会挤掉近期用户。历史窗口改用原始at的完整微秒、turn/role稳定游标；助手只出现一次。候选仍扫描、run/result仍fetchall，不宣称整个API常量内存。
- quote句末原先吃到下一句疑问；修硬句界后又核了逗号、闭引号与前置条件。授权先对完整原文等长掩码，再取句界，避免引用/转述中的“保存”变成敏感资料授权。独立28条矩阵通过，旧行为断言保留。
- 新now的微秒变化会改变repair_identity，已计3/6次仍会被严格门卫拒绝。选择持久化同epoch的业务时刻，保留原hash和预算。now/today锚定不等于整个snapshot冻结，事实有效期仍用当前Clock。
- 最初program_time普通put额外增加owner revision，进而改变三系统原生claim ID。改专用的owner/run/epoch/lease约束、仅ISO时间元数据写，不改语义revision；普通entity put仍照常更新revision。
- 最初提前落时刻会破坏取消/过期0步骤契约。最终仅在本次调用已安全记入diagnostic的同lease事务内保存锚点；成功和已诊断的network/503/zero_tool/契约失败稳定，unknown/cancel/expire/wrong lease不额外写。独立真实_call AST+纯Mock九边界通过，PG十三项由实现线验证。

时刻接线使`_call`追加可选`program_at`与固定安全元数据保存，这是payload生命周期的窄范围接线；没有修改模型构造、收费/预算/repair guard。超出原先按函数拆分的预期，需大脑结合P1同段诊断改动复核。最终整库验收结果以P2回执和CI为准，不把定向通过扩称整库成功。

## P10：本地交互和视觉证据

独立源码抽查未发现外域/API连接或危险HTML插入：字体/纸纹/牌面在本地，Markdown先清洗再转受限React节点。发现塔罗问题/牌阵/A/B未跨步骤传递，已抬升本地状态并补连续流程检查，仍是固定合成牌面。人工并排核对补回参考稿已有的现实前置句，未改运行时提示词。最终20单元、70浏览器和56份审计通过；视觉朱砂预算明确未验收。

## 冻结材料与未来合并

独立核验8份同步设计与源原始字节完全相同，四线P0基线blob与81个v1场景/rubric对象未变，便携证据见`prelude-audit.json`。只读对象级配对预检没有更新ref/工作文件；预检树未经集成验收，后续头变化必须重查。完整锁、`consultation.py`的语义接线及四线合并回归仍留到大脑批准后。
