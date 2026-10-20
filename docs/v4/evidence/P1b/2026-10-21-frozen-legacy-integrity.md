# P1b 冻结 legacy 字节完整性修复候选

时间：2026-10-21 00:56 北京时间。审计 [Core job 118741355281](https://github.com/JerryandShawn/zhiming/actions/runs/39455553086/job/118741355281)，head `dedce10956d05c5dc4fc847e5ae12d6525cee4d4`、CI合并对象 `1b03c1b929d6cf15ef943db9f1facc3aafd676f5`。该次Core运行553项/1070.621秒，唯一失败为 `test_exact_102_legacy_ids_map_to_defined_current_scenarios`，不能称CI通过。

## 原因与最小恢复

这不是CRLF差异。提交 `5ed56de` 给冻结 `tests/legacy/test_quality_v6.py:FakeClient` 与 `test_review_v6.py:_Client` 各新增一行 `_zhiming_offline_transport=True`。质量文件的真实Git blob SHA256因此为 `3232cf04473d07c11372a9e51b0e5e01acafd3d2d47e231e464734f1ead6fe1b`，冻结值为 `8c8479981e05ddf6ca46bbbbf6298bdbe06636ceba5f129a38e0db35d10fa6ac`；review也独立不符，CI在首个不符处停止。

两个文件恢复到 `03514f7` 的**原字节**。质量SHA256恢复为上述8c847998，review恢复为 `2d615351b6c11fbeb055b1dcac6e1c0e6ecccbab5c9965332ee639ff102b83d5`。`CORE_V3_BEHAVIOR_COVERAGE.json` 及原严格架构断言完全不改，不新增特例、忽略标记或重新签署基线。两文件显式 `-text` 防止跨平台转换；普通可变测试保持全局text=auto/eol=lf。原有真实请求禁用守卫和非冻结替身标记不变。

当前CI只静态读取这两份冻结文件枚举原102个ID，不执行退役控制器。因此不新增legacy执行harness，也不为了通过CI重新修改冻结内容。

## 验证

- `python -m unittest tests.test_core_architecture -v`：**6 tests，0.693秒，OK**，包括原102个ID到真实新场景的严格映射检查。
- 逐一读取清单11份源：SHA256与冻结清单相同，原字节与03514f7相同。
- `git hash-object --path=<file> <file>`（不写入对象）所得拟提交blob与 `git rev-parse 03514f7:<file>` 相同；不仅比较AST等价。
- AST枚举严格为102个原ID，逐一与manifest entries相同。
- `git check-attr text eol`：仅两文件text=unset；正常非冻结 `tests/test_agent_v5.py` 仍text=auto/eol=lf。
- `git diff --check` 通过。结构化全11文件SHA/Git blob见同名JSON。

本机目录为 `zhiming-v4-p1b`，验证基底 `a662c63`；远端head通过主代理的发布流程映射，最终新头CI仍待运行。本片没有运行新一轮全部Core/v4回归，不能把旧CI的552个通过当成修复后完整验收。无供应商请求、飞书发送、服务器访问、迁移或新依赖；PR保持草稿，由主代理提交和发布。
