# L1 时间基础层：可计算换算与交叉核对

范围：最新 `18_提示词增补包/P8_增补_时辰校正.md` §C 与 `17_深度研究_算命Agent架构v2.md` §2。只做准确出生记录及不确定时刻的时间换算与盘面分支；不调用旧评分、前三或合成命中率。旧U9证据保持冻结。本模块不确认出生资料，不调用模型、数据库、飞书或外部运行时服务。

## 接口与口径

`charts.time_basis.resolve_birth_instants(date, reported_time, place, clock_basis)` 接收明确阳历日期、时分（可带秒）、已确认的IANA时区与 `clock|standard|unknown`。`place.tz` 必填，不能从城市猜时区、不能默认UTC+8。返回JSON-ready列表：有效UTC瞬间，或明确的 `nonexistent` 项。有效项保留钟表时、标准时、UTC偏移、DST分钟数、fold、输入假设和时区文件SHA/IANA版本。未知钟表依据在DST中生成两种物理UTC假设；重复时刻生成两个真实UTC，等价假设合并但保留原假设列表。不存在的钟表时刻不自动挪后一小时。

`solar_time(instant, lon)` 同时输出标准时、地方平太阳时和地方真太阳时。标准时按时区的 `utcoffset - dst` 求得，不固定减一小时；经度修正为 `4*lon - standard_offset_minutes`，均时差用具名 `noaa-meeus-julian-century-equation-of-time-v1`，在真实UTC瞬间求值。真太阳时是同一瞬间的另一种时钟坐标，不是改变UTC。

`time_basis_candidates(date, reported_time, place, clock_basis, precision='reported'|'unknown')` 返回 `.items`。各项的年/月柱来自真实UTC+8瞬间的精确节界，日/时柱来自所声明的标准或真太阳坐标，统一使用 `sect=1` 晚子时23:00换日。纯计算 `pillars` 是权威；`coordinate_datetime` 是所选口径时钟，`calendar_datetime` 是真实UTC+8时钟，两者不能混用。节界±2分钟标记只看真实瞬间，不能拿平/真太阳时去移动立春。

按日柱/时柱/月柱组合去重时，`source_variants` 保留所有真实UTC、口径、经度修正、时区和节界来源；`basis_options` 列并存口径。代表项不是默认选派，`selected_basis=null`。同柱不能证明紫微命宫或起运时刻相同，后续wrapper必须保留来源分支，不能只因八字三柱相同就抹掉紫微或起运差异。不同口径导致不同时柱时并列；时柱相同时仅说“时柱稳定，无需按时柱校正”，不自动写入资料。

未知时间使用十二时辰中点及十二交界两侧共36个钟表采样，显式标 `not_continuous_coverage`，不声称覆盖连续全天的所有变化。当前区间输入由调用方分点传入本纯函数；本模块没有扩展现有 `TimeBranch` 枚举。

兼容字段 `civil_datetime/timezone_offset/engine_longitude` 只用于显式口径诊断，不代表重新确认的地点。`civil_datetime` 是标准时分钟坐标，真实UTC以 `utc` 字段为准；非整分钟记录会标 `legacy_args_compatible=false`。有效经线是程序实现单次修正的参数，不能写成真实地理经度。新wrapper应优先使用纯 `pillars` 与两个明确时钟，避免重复经度修正和sect1/sect2混用。默认v3引擎、适配器和worker均未修改。

## DST与历史时区

跨平台来源选择已修正：每次调用读取当前 `PYTHONTZPATH`，显式非空覆盖只接受绝对目录，按顺序查找实际文件；导入模块后修改环境变量也生效。非法相对目录、显式目录缺少目标文件均拒绝，不静默改用别的数据。显式空串禁用系统目录，只允许包数据。没有显式覆盖时优先使用已安装的 `tzdata` 包，记录包版本、IANA版本和实际文件SHA，避免Linux系统旧数据库抢先覆盖部署所锁版本。

仅在没有显式覆盖且包不可用时才读取系统目录，标为 `system_unpinned_fallback`，明确写出“系统数据未锁定、未证明跨平台一致”。本函数记录包版本但不冒充已校验部署锁文件；主线仍须安装锁定依赖。新增9个展开用例使用临时目录和真实上海tz文件，故意标记系统版本 `unpinned-system-test`，复现系统/包冲突，核对包优先、导入后显式覆盖、空覆盖、无包回退及失败分支。Core/Charts桥也在伪旧系统目录存在时比较同一包文件的fold瞬间与ID。该模拟不是Linux CI实跑结果。

真实IANA数据验证了下列规则；全部是合成输入/公开历法日期，没有使用用户出生资料。

| 场景 | 实际观察 |
| --- | --- |
| 1986-05-04、1988-04-17、1991-04-14 | 01:59为UTC+8；02:30钟表时不存在；03:00为UTC+9，对应标准时02:00。 |
| 1986-09-14、1988-09-11、1991-09-15 | 01:30出现两次，相隔一小时；第一次标准时00:30，第二次标准时01:30，两个fold都保留。 |
| 1988-07-15 09:30，不确定依据 | “当时钟表”对应标准时08:30；“已经是标准时”对应09:30；并列并需确认。 |
| 1940-07-15 上海09:30 | 锁定数据返回UTC+9/DST60分钟、标准时08:30；明确标历史数据可能有误差。 |
| 1979-07-15 香港/台北09:30 | 两个明确IANA时区均返回UTC+9/DST60分钟、标准时08:30；没有套用上海规则。 |
| 乌鲁木齐，1995-03-10北京时间09:40，经度87.625° | 经度修正−129.5分钟；Meeus均时差约−10.508分钟；真太阳时约07:19:59.54。标准时为巳，真太阳时为辰，真实UTC相同。 |

历史上海有不同机构未同时采用夏令时的记载，所以tzdb结果只是可追溯的历史规则，不替代出生记录或当时钟表依据；1949年前强制标提示。[IANA上游asia原始规则与注记](https://github.com/eggert/tz/blob/main/asia)、[Python ZoneInfo官方文档](https://docs.python.org/3/library/zoneinfo.html)分别支持规则来源与fold/数据源机制。

## NOAA六日期公开数值

原始文件是 [NOAA官方全年太阳计算表](https://gml.noaa.gov/grad/solcalc/NOAA_Solar_Calculations_year.ods)，由[官方计算说明页](https://gml.noaa.gov/grad/solcalc/calcdetails.html)链接。下载文件390,343字节，SHA256 `28b4c196700e2a57e0ff32c4c88729d5506e3b8f425700ece71397e801a0b0a6`，只放在忽略目录 `private/time-basis-reference/`。测试知识表只保存六个已公开数值及出处，没有把整份表入Git。

从原始ODS的 `content.xml` 读取 `Calculations` 表缓存数值，不执行表内公式，不用本实现重算参考值。原表设置为2010年、标准UTC偏移−7、当地正午12:00，因此每行对应UTC19:00。包含2月中旬与11月初均时差极值附近。

| UTC日期时刻 | 原表单元 | 官方缓存均时差（分钟） | 本实现绝对误差（分钟） |
| --- | --- | --- | --- |
| 2010-01-15 19:00 | V16 | −9.50469392310526 | 1.78e−15 |
| 2010-02-15 19:00 | V47 | −14.1379287302671 | 3.02e−14 |
| 2010-04-15 19:00 | V106 | 0.0208955169080454 | 4.86e−17 |
| 2010-06-15 19:00 | V167 | −0.522779190331529 | 0 |
| 2010-09-15 19:00 | V259 | 4.84100803902021 | 0 |
| 2010-11-03 19:00 | V308 | 16.4768579211255 | 7.11e−15 |

六项均满足≤0.5分钟，最大差约3.02e−14分钟。**这是外部官方公开缓存数值对照；原表与本实现同属Meeus数学体系，不是独立天文观测、独立物理模型或出生时刻实测。** 接近机器精度只说明对应公式和符号实现一致，不能解释成真太阳时实际准确到该精度。EOT符号明确为真太阳时减平太阳时。[NOAA官方简化太阳方程PDF](https://gml.noaa.gov/grad/solcalc/solareqns.PDF)也给出这一符号与时间换算；该PDF的简化傅里叶近似没有冒充本次原表缓存数值来源。

## 验证与交主线

最终定向命令 `pytest tests/v4/test_p8_time_basis.py tests/v4/test_p8_time_basis_process.py -q`：36 passed、0跳过、1.92秒。其中34个展开用例覆盖时区来源优先级、历史换算与NOAA数值，两项Core桥在真实Charts环境执行8项原生盘面测试，并比较同一tz文件在Core/Charts得到相同fold物理瞬间与ID。8项原生测试也单独运行通过。Ruff E/F/I/B/UP/SIM与7文件默认format通过；新增文件均≤400行、函数≤60行、行≤120字符。

本模块源码、测试与参考表manifest digest为 `37decbe7ace645ed42e98fd11f76482cad1bea5170f5ab25e3beddd1b65ba237`；最终运行前后未变。机器证据 `time-basis-crosscheck.json` 含每项命令、原表缓存读取、时区SHA/IANA版本、历史样例和风格检查；原输出见 `time-basis-tests.txt`、`time-basis-native.txt`、`time-basis-ruff.txt`、`time-basis-format.txt`。修复前27项运行的摘要作为历史验证保留，当前验收以36项为准。旧三套Hermes引擎、旧ChartAdapter与旧worker相对HEAD换行归一后全部不变。

已核实 **Core锁与Core运行时已有tzdata==2026.5（IANA2026e）；仅Charts锁/运行时缺失**。本次Charts子进程通过显式 `PYTHONTZPATH` 只读Core包的zoneinfo数据，没有安装或改动任一venv。主线仍需把Charts同版本依赖锁定、安装并在Linux CI验证；当前证据只证明本机两个解释器在同一数据文件下结果一致，不能声称Linux CI已通过。`rectified`领域枚举与资料确认迁移仍由主线处理，本模块未改domain、locks或资料数据。
