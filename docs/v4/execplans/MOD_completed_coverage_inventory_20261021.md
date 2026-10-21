# MOD：完整离线模块的覆盖范围盘点

## Purpose / Big Picture

33号储备要求新代码覆盖至少90%。已有各模块报告使用不同范围，不能把局部高分当作本轮全部产品覆盖。
本盘点先保留最新27组普通回归三遍，再在北京时间45–59分窗口做单进程插桩回归，列出本轮新增产品逐文件覆盖及不足。
全部使用合成输入；不读取盲集B或私有75条校准材料，不接PG、模型、平台或运行入口。

## Context and Orientation

唯一工作目录为 C:/Users/Administrator/Documents/Codex/zhiming-v4-mod，分支v4/mod-organize。
启动基底8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd既有文件不可更改。
复用 tools/mod_week/completed_regression.py 的SUITES、source_snapshot、environment及window_time，
后者通过显式Asia/Shanghai时区校验全量启动分钟。覆盖分母只选本轮A状态的产品Python，排除测试与旧产品。
tools/calibration_v3与tools/eval_material_v23是模块纯工具，也单列纳入；不把未执行入口隐去。

## Progress

- [x] (2026-10-21 09:36 +08:00) 本轮373个新增Python全部通过Ruff、format、AST单文件400/函数60行检查，基底非A路径0。
- [x] (2026-10-21 09:48 +08:00) 27组普通三轮各12267通过，511快照各轮/跨轮相同。
- [x] (2026-10-21 09:50 +08:00) 插桩12267通过125.18秒，09:48合法启动、511快照与普通回归相同。
- [x] 发布191文件完整分母、57不足文件及原始缺行/分支；新增三份只读边界计划继续储备。
- [x] (2026-10-21 10:51 +08:00) 晨报产品修复与104项后补后新三轮各12371/532；插桩另12371通过，192分母综合92.392845%、分支86.431412%，46文件不足90%。

## Surprises & Discoveries

局部报告使用综合(行+分支)覆盖，部分分支仍低于90%；现有数字不能直接组合成全PR覆盖。
完整盘点确认总综合91.494985%但分支85.029940%、57文件不足90%；未执行CLI保留0%。
coverage默认规则排除81行，未更改排除配置，也不把协议声明说成已执行。
10:51更新：新192分母、532稳定快照与46不足列表另存MIDDAY报告。只增加current_manifest一份，旧分母无删除；
实际config_files_read=[]、omit=null，默认排除仍81行；CLI入口已由真实公开调用测得，子进程覆盖未伪并。
普通回归期间新发现的真实反例必须保留，不能移出已登记suite掩盖失败。

## Decision Log

2026-10-21 09:54 +08:00：公开完整分母和逐文件不足，后续优先记忆变更、坏历法端口、晨报来源证据；不重开冻结B。
2026-10-21 10:40 +08:00：本次产品/测试已有实质后补，完整验证需要新报告；同样列未执行文件、缺失分支与coverage实际配置，不把专项覆盖拼成新总体。
2026-10-21 09:39 +08:00：只测明确的27个模块目录，报告叫“本轮新增产品、27组离线测试范围”，
不称整个仓库或真实接线覆盖。插桩耗时与普通回归性能严格区分。
覆盖率是后续定位工具，不为分数构造不可能的私有态，也不修改冻结Q5或开封B。

## Outcomes & Retrospective

已完成27组普通三轮12267与插桩12267，191新增产品行93.905843%、分支85.029940%、综合91.494985%；
57文件综合不足90%、81默认排除行、CLI入口0%均公开，不称逐文件达标。源快照完全相同；无PG/平台/质量结论。
10:51新盘点另外记录：192产品、12371测试、532快照，行94.615884%、分支86.431412%、综合92.392845%；
46文件仍不足90%。两次报告保留原身份，不能把新百分比套回191产品或旧源。

## Concrete Steps

在上述工作目录清provider keys、关闭tracing，使用已锁定Core Python3.11与现有coverage。

    python tools/mod_week/completed_regression.py --output docs/v4/evidence/MOD_2026-10-21/MORNING_completed_regression_0945.json --rounds 3
    python -m coverage run --branch --source=mingjing_core,tools/calibration_v3,tools/eval_material_v23 -m pytest <SUITES中的27个tests/v4目录> -q --basetemp=private/mod-week/tmp/completed-coverage-0945

coverage数据只放private/mod-week。使用coverage API的json_report(morfs=新增产品路径列表)导出，
路径列表来自git diff --name-status基底，仅A且为mingjing_core或上述两纯工具目录的.py文件。
报告记录命令、解释器/coverage版本、源快照前后SHA、实际输出及逐文件coverage summary/缺失行和分支。
所有公开JSON显式UTF-8、LF；原始观测不回写旧报告。

## Validation and Acceptance

对应07中的M/R/F/TM/X/P场景只作模块级支持，不宣称产品脚本验收通过。
普通三轮原始pytest退出码为0、每轮源路径集合/字节稳定、跨轮相同；失败时保留输出，不跳过失败项。
插桩同样需要pytest为0与源快照零漂移；分母中未执行产品照实记0，不以合成成功替代业务质量。

## Idempotence and Recovery

重复测量使用新报告路径和private数据文件，不覆盖历史证据；没有迁移、配置或业务写入。
若超时或窗口结束，只保留真实失败/未完成并继续其他离线储备。

## Artifacts and Notes

证据统一放docs/v4/evidence/MOD_2026-10-21/MORNING_*0945*；后续接线索引记录明确范围。
没有新增运行时依赖，不修改原业务接口；测量辅助只读当前源，不读取私有材料正文。

## 修订记录

- 2026-10-21 09:39 +08:00：创建全量覆盖盘点，避免把局部90%误述为全部达标。

- 2026-10-21 09:54 +08:00：更新三轮与覆盖实际结果、57文件不足、默认排除及后续公开输入优先级。
