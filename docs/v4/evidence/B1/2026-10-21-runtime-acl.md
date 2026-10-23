# B1：运行角色额外表权限拒绝门

记录时间：2026-10-21 09:48（北京时间，UTC+08:00）。本片仅强化 `PostgresPort._runtime_safe` 与 B3 `writer_permissions` 的只读有效权限判断；没有自动撤正式权限、迁移、恢复新包、服务器访问或真实模型/飞书请求。B1仍No-Go。

## 真实问题与最小改动

原两门检查TEMP/schema CREATE/ownership/继承及表CRUD，却只对两本账本拒绝部分额外表权限。业务表另外获得TRIGGER、REFERENCES、TRUNCATE时，或账本额外获得REFERENCES时，检查仍可报告安全。root确认运行writer仅有既定四项CRUD，不能拥有这些额外权利。

两门各在现有elevated聚合中增加一个EXISTS：枚举 `pg_tables` 中mingjing_core/public的有效表，使用quote_ident限定实际关系名称，拒绝任何有效TRUNCATE、REFERENCES、TRIGGER。它同时观察直接授予和PUBLIC继承；不依赖“执行过grant”的推断。已有TEMP行及全部旧判断保留；仅2处聚合变化，无新receipt字段，原5个实际拒绝探针及计数仍为5。

## 先红后绿

首次环境启动为8 setup errors /2.17秒：Windows进程清环境留下空PGSERVICE，libpq拒绝空service文件名，尚未创建本例资源。改为真正移除进程Env项；不把setup错误计为业务红，原件保留。

旧SQL真实业务红分两组：**8 failed /79.27秒** 与 checkpoint账本 **2 failed /22.21秒**。每例都先证明安全基线，再给自身随机恢复库writer或PUBLIC追加一项权利；确认实际has_table_privilege=true后，两门仍分别误报 `incremental_safe=true`、`restore_safe=true`。业务TRIGGER/REFERENCES/TRUNCATE及两本迁移账本REFERENCES共10种绑定全部实证。finally仅撤本例新增授权，恢复安全基线；不触任何正式库。

加最小只读SQL后组合 **28 passed +4 subtests /194.93秒**，退出0，0失败/错误/跳过/警告：新ACL10、原TEMP2、原PG port5、原B3 PG11。新测试的两门都拒绝额外权限，撤回本例授权后恢复通过。旧测试和断言未改，B3原5探针计数实际仍为5。JUnit的tests=32包含4子断言，主用例仍为28。

    python -m pytest tests/v4/release/test_b1_incremental_runtime_acl_pg.py tests/v4/release/test_b1_incremental_runtime_temp_pg.py tests/test_core_incremental_pg_port.py tests/v4/release/test_b1_restore_proof_pg.py -q

实际PG为Windows loopback15，每例独立随机库/owner/writer，真实pg_restore/固定b9 4→7/最新撤销和收据重放准备后再测权限。未构造正式NativePort或访问stage/live；模型/渠道凭据移除且追踪关闭，只占1窄进程。严格Ruff、120格式、尺寸与diff检查通过。

## 最终代码指纹

| 文件 | SHA256 |
| --- | --- |
| tools/core_incremental_pg.py | `903c69d2d743f0cb606c241295a69045b78f8f3a324adad3c601b1dbbdd663c6` |
| tools/b1_restore_proof_pg.py | `fa1391fa9ab30d5351dfa544e5f8635892affe3272ca42b033508da94d7d1db7` |
| tests/v4/release/test_b1_incremental_runtime_acl_pg.py | `ca9e93a4c357acac91a6692c554ce36b8b7efb896406814ec83273360f5e3877` |

## 原始证据

| 私有原件 | 字节数 | SHA256 |
| --- | ---: | --- |
| private/b1-restore-proof-20261021/runtime-acl-red.xml（环境setup） | 7111 | `10cd17525bc3f578d4d8ecdb2af9e95f1bbe009339df313449860cea4679f1ef` |
| private/b1-restore-proof-20261021/runtime-acl-red-2.xml | 8105 | `70b67956db1c527403f0ee50e2d9f7f67d5a8ad09e83134eedb1d6ac5b72b30b` |
| private/b1-restore-proof-20261021/runtime-acl-red-checkpoint.xml | 2240 | `a5b8d9f9de1093e176ab8aa1c6cac9ae10786682cd124b83506cf68e83cd003b` |
| private/b1-restore-proof-20261021/runtime-acl-green.xml | 5274 | `0db17ac19ddc80aee962f0cc188185f843ab7bf1e8f133f8993be28f95c28ce3` |

原JUnit保留+09时区，不重写：环境开始10:42:26+09对应北京时间09:42:26；业务8红10:42:51+09对应09:42:51；checkpoint2红10:44:43+09对应09:44:43；绿组10:45:23+09对应09:45:23。公开记录均按北京时间。

## 未验证与独立后续

此片不是Linux、服务器权限、完整CI或stage放行证明。正式receipt仍须受保护路径/hash和人工审查；这些JSON不是密码签名，不能把手填观察视为真实执行。

schema有效USAGE缺失时旧方法究竟误放行还是已因关系名称解析失败关闭，仍需下一独立真实PG片判定，不混本片28/4数字。App/B3目前也未全面核venv包文件及pyvenv.cfg写保护，已单独报root，未冒称实际venv被篡改。环境两次恢复上限和Linux阻塞保持；没有扩大正式访问授权或修改固定b9。
