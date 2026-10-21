# B1：缺 schema USAGE 时明确拒绝类别

记录时间：2026-10-21 09:55（北京时间，UTC+08:00）。本片是拒绝分类改善，**不是发现或修复真实误放行**。不自动修改正式权限，B1仍No-Go。

## 真实旧行为

先做两schema（mingjing_core/public）×两个唯一有效来源（直接writer/PUBLIC）四种独立真实PG绑定。每例先准备固定b9 schema4备份恢复→迁7→最新撤销/收据重放的随机库；显式撤除另一个来源，再证明唯一来源有效。撤除唯一来源后实际 `has_schema_privilege(...,'USAGE')=false`，避免只撤PUBLIC却仍有直接授权的假反例。

旧两门四例均返回诊断类别 `sql_insufficient_privilege`，关系名称查权已由PostgreSQL失败关闭；**没有观察到accepted/true**。最初4 failed /39.46秒仅因为新增诊断断言要求明确False/固定业务码，不能称安全漏洞红或既有安全回归。finally恢复本例唯一有效来源后重新通过。

## 获批最小变化

两个权限门在任何table privilege查询前，单独只读查询两个schema的有效USAGE。缺失时增量检查返回False，B3沿用固定 `WRITER_OWNERSHIP_OR_DDL` 拒绝码。正常情况仍执行全部ACL/TEMP/ownership/账本只读/CRUD以及B3原5个实际拒绝探针，未改变探针定义、计数或receipt ABI。

旧PG port假连接只新增该SELECT的正常safe响应和Factory.schema_usage默认true，另增false时不进入table privilege查询的独立反例。原5个测试函数AST与修改前HEAD逐项完全相同，旧断言不删不改；不模拟真实PG业务。

## 最终窄验证

**10 passed +4 subtests /39.71秒**，退出0，0失败/错误/跳过/警告：4真实PG、5个原PG port用例及1个新stub。JUnit的tests=14包含4子断言，主用例仍为10。没有重复前片ACL28/4或全部B3 PG11，亦未跑全库。

    python -m pytest tests/v4/release/test_b1_incremental_runtime_usage_pg.py tests/test_core_incremental_pg_port.py -q

真实验证来自Windows loopback PG15，仅本例随机库/角色；测试中的GRANT/REVOKE只作用自身新库，不执行任何正式权限修复。模型/渠道凭据移除、追踪关闭，服务器/真实模型/飞书0。严格Ruff、格式、尺寸及diff检查通过。测试位已于09:54释放，未占10:00宽回归位。

## 最终代码指纹

| 文件 | SHA256 |
| --- | --- |
| tools/core_incremental_pg.py | `53003be5d233aee771d8444314cba2d6eb6337c85cf9e850d41f74dcdbd5f257` |
| tools/b1_restore_proof_pg.py | `d77a0a3b1e18bab527dd40936fe0a0c379d93545ec47cc4451926895dd96eae6` |
| tests/test_core_incremental_pg_port.py | `e4ac3b3ea3dbfe339a9d75ab3b24e5b1310b70f8ef0ca0760fb776e6d21662dc` |
| tests/v4/release/test_b1_incremental_runtime_usage_pg.py | `70fe7e2d466a26b6709b879d5283eb41acaa9df8be06e00bd87e9e8eab99d94b` |

## 原始证据与未验证

| 私有原件 | 字节数 | SHA256 |
| --- | ---: | --- |
| private/b1-restore-proof-20261021/runtime-usage-diagnostic.xml | 4508 | `3f5f4913caffcc68d8fd72f07777170ba897d23f271c08155949ab34386f1b52` |
| private/b1-restore-proof-20261021/runtime-usage-green.xml | 1954 | `dd0d09f430b1aaf8f89b3c8cf4eb565f2b63c73bffb0d526b3e3c3601df6938e` |

原JUnit+09时区保留不修改：诊断开始10:52:06+09对应北京时间09:52:06；明确分类组10:54:15+09对应09:54:15。公开记录使用北京时间。

此片不证明Linux、正式权限、完整CI或stage放行；原SQL已安全拒绝和新明确拒绝是两种独立观察，不将其包装为放行漏洞。固定b9、正式库/角色/端口、五门及两次环境恢复上限均未改。root统一提交/推送六件，当前没有其它工作树、迁移、依赖或服务器变更。
