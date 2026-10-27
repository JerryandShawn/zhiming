# 塔罗服务来源：具名Clock迁移审阅 v1

本契约补充牌阵只读资产v1的出处核对，不是抽牌入口或运行服务注册。资产
`mingjing_core/knowledge/p8_tarot/spreads_v1.json`及其原来源SHA保持不变。
审阅元数据：`mingjing_core/knowledge/p8_tarot/service_clock_review_v1.json`；
纯静态检查器：`charts.benchmarks.tarot_source_review.review_service_source(text)`。

## 历史来源与当前源码分别核对

原资产引用的服务全文UTF8/LF SHA为
`603d961da03bc076c3272ffc40350a575ed6423e06716ee01f3db1f0b10b5ee0`。
这仍是当时的真实出处，不把它追写成由新实现生成。

实际从GitHub读取的合并快照`5bbd2fccfe392e30dc4b1686bd06acf8d12225c7`中，
同一路径`mingjing_core/adapters/tarot.py`的blob为
`66600110660608840d8182474ee6752f0204613c`，全文LF SHA为
`742d022d2368420f51870c2df4b7b50e5802966006f671f95a0fd1ce20e8b9ad`。
这是读取既有快照，没有在本机执行合并或修改旧adapter。

完整diff恰三处：删除datetime/timezone导入；添加项目get_clock导入；
模块函数`_stamp`从`datetime.now(timezone.utc).isoformat()`改为
`get_clock().now().isoformat()`。其他文本逐字一致；整个TarotService类AST相同，
包括owner/subject、A/B、固定顺序、手动牌面、重复请求与ready门槛。
`_stamp`属于模块函数，不宣称它的AST也相同。

只看到同一个SHA不够：Clock版本先核精确新全文SHA，再恰一次逆向三处迁移，
重建全文必须严格等于历史603 SHA，还要比较完整TarotService类AST。
任一未知版本、额外注释或行为改动、替换重复/缺失、无法重建，均拒绝等待审阅。
不采用任意两个hash皆可的白名单，不忽略整文件/整个函数的变化。

原603检出返回`checkout_basis=historical_source`，
`reviewed_clock_checkout_verified=false`；只说明历史来源完整性。
实际742检出才返回`checkout_basis=reviewed_clock_migration`和对应true。
返回中总有`runtime_execution_verified=false`、`clock_dependency_verified=false`；
这一静态审阅不能证明DB/服务行为、外部依赖身份、Clock注入者或实际主线集成。

## Clock范围与失败含义

只读审阅了本机`timekit.clock.Clock.now`的“时区感知UTC”接口，
SystemClock使用UTC，FrozenClock将时刻转为UTC。静态测试只提取已核 `_stamp`，
使用真实FrozenClock的固定2026-10-21 UTC时刻验证isoformat输出；不执行整个服务、
不导入adapter、不连接DB、不改全局时钟。

Clock文件本地观测SHA另记元数据；本检查器不将其当作当前运行依赖认证。
外部Clock实现或`set_clock`注入者变化，即使adapter全文相同，也在本次已验范围之外。
因此不能把AST相同写成全部时间副作用等价、线上行为通过或时区正确性已验收。

错误均为固定枚举，不含源码正文：

| 码 | 含义 |
| --- | --- |
| P8_TAROT_SOURCE_REVIEW_REQUIRED | 未知当前源码，停止自动映射 |
| P8_TAROT_SOURCE_REVIEW_PATCH_MISMATCH | 精确迁移位置重复或不存在 |
| P8_TAROT_HISTORICAL_SOURCE_MISMATCH | 不能重建原来源 |
| P8_TAROT_CLOCK_SOURCE_MISMATCH | 重建的迁移版本不等于已核快照 |
| P8_TAROT_SERVICE_LOCATOR_MISMATCH | 类定位不唯一 |
| P8_TAROT_SERVICE_SEMANTICS_CHANGED | 完整类AST不相同 |

出处是两个具名项目源码blob及本项目Clock接口，流派为项目原创反思方法；
它不是Waite原刊或牌义效度证据，不产生实际牌面或c/r/t别名。
无授权/撤销、固定牌面或原78牌义变更。当前CI通过与否仍按新HEAD实际结果记录。
