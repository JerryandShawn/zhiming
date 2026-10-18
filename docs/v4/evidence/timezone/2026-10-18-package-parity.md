# Charts tzdata 锁定与双系统检查准备

日期：2026-10-18，Asia/Taipei。依据用户授权与大脑23号文件：Charts锁定与Core一致的tzdata2026.5 / IANA2026e，增加Windows/Linux一致性CI。本轮只改本机代码/Charts依赖；未改生产配置、P8算法或前端。

## 已完成与实际结果

`requirements-charts.lock`只增加tzdata2026.5及说明，其余既有Charts锁定版本未变，本机仅新增tzdata。Core锁不改。原Charts锁是纯版本锁，本轮不把单包hash混入该文件以误触全closure的pip require-hashes；另建仅含tzdata的`tools/timezone/tzdata.lock`，使用官方wheel/sdist两个SHA256。

检查工具不导入排盘算法：在独立进程清空ZoneInfo缓存并强制包数据源，用6个TZif资源hash与21个历史/DST边界金标核验；覆盖上海1986/1991夏令时、纽约/伦敦缺失及重复时间、加德满都15分钟变更、阿皮亚跳日、Lord Howe半小时DST。

本机Windows真实Charts安装仅tzdata2026.5成功；5项unittest全部通过。Core与Charts分别fresh-process的21项数据摘要一致：

    f66f063a04cb9fb1a5238bac645d1aaea32957502bd3bb782c670ac5df578df2

回归还验证错误版本/重复pin/缺hash/资源篡改会失败，伪系统TZPATH和既有ZoneInfo缓存不能掩盖包规则。Ruff E/F/I/B/UP/SIM、format120、diff及UTF-8/LF检查通过。检查工具232行、最长函数28行；测试110行、最长函数20行。

## 可重复命令

在仓库根目录，以独立Charts解释器执行，仅安装时访问PyPI，无模型调用：

    uv --no-config pip install --python .venv-charts/Scripts/python.exe --no-python-downloads --require-hashes --no-deps --only-binary=:all: --default-index https://pypi.org/simple -r tools/timezone/tzdata.lock
    .venv-charts/Scripts/python.exe -m unittest discover -s tests -p test_timezone_data.py -v
    .venv-charts/Scripts/python.exe tools/verify_timezone_data.py
    .venv-core/Scripts/python.exe tools/verify_timezone_data.py

检查报告原件位于task工作目录`work/daytime/timezone-charts-windows.json`与`timezone-core-windows.json`；安全副本见同目录`2026-10-18-windows-charts.json`。21项金标为合成时间边界，不含用户出生信息。

独立`.github/workflows/timezone-data.yml`在Windows/Ubuntu、Python3.11上仅安装这个哈希包，运行相同测试及fresh检查，并上传各自摘要。平台均须匹配同一固定摘要，不能靠各自生成不同金标过关。

## 未验证与发布边界

远端提交`90849c60cf6772c1492df9465c0de745d857f54d`的[双系统CI 39119854074](https://github.com/JerryandShawn/zhiming/actions/runs/39119854074)已success：Windows job117653052902、Ubuntu job117653053156均完成哈希安装、5项回归、fresh-process摘要核验与产物上传。后续Journal/文档提交不改变这五个锁/工具/测试/workflow文件的验证字节。

本检查覆盖锁版本、包数据和ZoneInfo行为，不代表全套Charts依赖/算法在两系统一致。普通Linux进程仍可能优先系统TZPATH；本轮未改默认运行时或服务器。完整算法/实际时间口径仍归命理线。

B1固定候选b9a89b6不含本次修复，不能静默补入旧包。由大脑裁定单列后续或批准新候选重跑CI/stage；当前不改候选、不执行部署。
