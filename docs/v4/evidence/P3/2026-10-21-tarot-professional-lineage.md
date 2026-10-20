# P3 固定塔罗 c/r 与撤销闭包

时间：2026-10-21 01:58 北京时间。仅本机隔离 PG15 和 ScriptedPort，未访问服务器、模型供应商或真实飞书。

真实已完成 `tarot_read`、受保护缓存、当前 native draw/可选实际 reading、冻结原创 deck/meaning/method、牌位/方向/card_snapshot 与原话 SourceRefs 共同证明一份 artifact 和每张牌的 interpretive_claim。未揭示牌不注册 c/r；实际 reading 不存在时保留 null。长期 mirror 使用 source_ids、source_versions 和独立 source_ranges 元数据，不存缺 quote 的伪 SourceRef，不复制用户原话。r 的含义为原创象征反思，not_user_fact=true，不生成 fact；牌阵自动关联的事项也不因此取得 case_update 权限。

同 run/epoch/native 的重复读牌复用 mirror ID，不重新洗牌。输入、native 牌义版本或 card_snapshot、mirror 正文/来源/运行批次被篡改时拒绝；不放宽 chart 原有 professional 证明保护。

native cancel 同事务清空私有 runtime_step、塔罗 mirror 与步骤/事件正文，保留原牌阵和 U7 的 24小时限制；native case aggregate 版本进一步阻止已取消牌在最终提交中继续采用。delete 通过实际缓存/mirror/当前 epoch 的成功 start 回执及持久 request 查派生运行，清空运行结果、回复、步骤/事件、mirror 和 outbox；取消后再删除仍找得到原 start run。普通原话及同一次实际 Runtime 的独立 memory_write 偏好仍有效。

验证记录：

- 相关目标 101 passed / 42.50s：当时新增16项及首片、U7、Chart接线、case索引、严格回填。
- 重构后 native 旧删除6项与新16项、Chart/case目标 46 passed、2 subtests passed / 24.92s。有1条现有 Starlette/AnyIO 依赖弃用警告，无跳过。
- 最终塔罗目标 51 passed：再补真实来源撤销同步清缓存/mirror，以及撤销无关片段后实际 Runtime 仍能沿用固定问题，全部模型输入不含已撤销正文。0 skipped、0 warnings。
- 新模块、Loop codec、工具边界与新增测试 ruff（120列 E/F/I/B/UP/SIM）、format、AST 文件≤400/函数≤60及 diff check 通过；native 旧文件保持最小改动，不整体重排历史代码。

实际 Runtime 正例输出 core4 的 c1/r1、used_claim_ids 有真实持久实体而 used_fact_ids 为空；删掉合成 assistant 后由严格 backfill 重建相同来源和 claim。实际模型 I/O 期间 native cancel 后无 final/assistant。待投递只在本机 prepare，删除后领取失败，真实发送为0。

范围：无真实模型质量结论，无服务器部署。专业别名不支持无完整来源或无法复核历史 deck 版本的牌阵；尚待下一次固定提交头全库回归。公共事件契约、P8/Charts、Finalizer、Runtime 均未修改。
