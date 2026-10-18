# 准确时刻的只读口径核对接口

> 历史说明：本页对应23号续作前的证据；当前默认口径、排除规则、运行时依赖状态及新检查见[P8续作回执](P8_23号裁定与剩余计算_阶段回执_2026-10-18.md)和e2-brain23-adjudication-2026-10-18.md。保留旧数值，不冒称当前状态。

用户2026-10-18最新D3：已有准确出生时辰，先以记录为准，核对夏令时、标准时/真太阳时、交节和晚子时。人生大事倒推放到最后；本入口不评分、不改出生资料。

`P8ChartAdapter(owner).time_basis(request)` 只经Charts子进程计算。请求含 owner_user_id、subject_id、revision、operation_id、as_of_date（调用方Clock确定）及birth。birth为 `{date, reported_time, gender, place:{tz:IANA,lon,lat}, clock_basis:clock|standard|unknown, precision:reported}`。出生地必须显式给定，不根据城市猜经度或偏移。revision必须非负整数（含初始revision=0）。

输出time_basis保留所有物理UTC瞬间、时区数据SHA/版本、钟表/标准/平太阳/真太阳坐标；去重的柱组合保留source_variants。`charts[]`逐来源计算八字与紫微，避免同柱误当起运/命宫相同。两种口径未选择默认；时柱稳定与全部柱稳定分别标记。不输出top_three，不进入人生事件评分。

八字年/月柱、司令经过日数与起运按同一物理UTC换为UTC+8；日/时按所选坐标、晚子sect1的23点日界。沿用的Yun方法仍是getYun(gender,1)，新时间入口保留秒。紫微把已换算坐标交给build(dt,0,gender,0)，明确标为预转换坐标；不会再次减夏令时或经度。紫微晚子为py-iztro index12默认日界，与八字sect1分开标明。默认v3依旧是既有地方平太阳时/旧日界行为，未修改。

5项进程测试与6项纯输入检查通过：owner在进程前拒绝；乌鲁木齐09:40标准巳/真太阳辰并列；1988-04-17 02:30不存在时刻不自动平移；秒精度保留；unknown不偷偷走事件评分。合成数据，0模型/0资料写入。命令：`CHART_PYTHON=<Charts Python> <Core Python> -m pytest tests/v4/test_p8_time_basis_entry.py -q`。

环境缺口：Core锁已有tzdata==2026.5；Charts锁和运行时缺失。同机验证显式借用Core安装的tzdata路径（测试专用PYTHONTZPATH），不修改两套运行环境。部署前由主线在Charts锁/环境安装同版本，并完成Windows/Linux相同数据的CI核对；不能把本机测试当作跨平台验收或页面接入。

独立复核与修复：精确秒起运覆盖后重新应用具名藏干，避免回退旧表；司令保留本次实际前后节界和节名。公开入口拒绝basic/week ISO日期而不在后端才失败，允许初始revision=0；新增断言保持。
