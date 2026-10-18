# 命盘页只读模拟数据：阿远

三份JSON都是本机真实排盘引擎对07号`default_synthetic`合成画像的计算输出，供前端离线开发；没有真实用户资料，也不是线上API快照。本线不改web/，不代替前端接线与交互验收。

按页面选择`ayuan_bazi.json`、`ayuan_ziwei.json`或`ayuan_astro.json`直接导入。`view.primary`是主盘引用列表，`comparisons`是盘面有差异的比较引用，`diagnostics`保留可展开核对项。一个Ref始终指向同文件`documents`里对应对象的`payload`。

```javascript
function readRef(sample, ref) {
  const doc = sample.documents.find(item => item.document_id === ref.document_id);
  if (!doc) throw new Error('Unknown sample document');
  let value = doc.payload;
  if (ref.path === '') return value;
  if (!ref.path.startsWith('/')) throw new Error('Invalid sample pointer');
  for (const encoded of ref.path.slice(1).split('/')) {
    if (/~(?![01])/.test(encoded)) throw new Error('Invalid pointer escape');
    const key = encoded.replace(/~1/g, '/').replace(/~0/g, '~');
    if (Array.isArray(value) && !/^(0|[1-9][0-9]*)$/.test(key)) {
      throw new Error('Invalid array index');
    }
    if (value === null || typeof value !== 'object' || !Object.hasOwn(value, key)) {
      throw new Error('Missing sample field');
    }
    value = value[key];
  }
  return value;
}
const primaryValues = sample.view.primary.map(ref => readRef(sample, ref));
```

太阳回归样例显式选用成都坐标作为合成练习地点；不表示真实阿远当年在那里，也不是按出生地或住处自动补地点。真实接线需取得明确回归地点。

页面映射：

| view字段 | 展示用途 |
| --- | --- |
| time_basis | 时区、DST、真太阳/北京时间坐标与确认状态 |
| primary | 真太阳时八字/紫微；西占实际UTC计算 |
| comparisons / diagnostics | 不同结果并列及其它坐标核对；数组为空可正常显示“当前无盘面差异” |
| rules / assessments | 已命中规则与全部条件，分别展示；false不渲染成已成立 |
| interactions | 程序已排序的时间关系、参与柱、领域、项目口径与来源边界 |
| flying | 紫微宫干起点、四化星、真实落点、自化及几何对宫；缺失保持未解析 |
| transits | 西占入相/精确/出相窗口，注意剪裁与空结果 |
| timings | 具名次限和太阳回归，读取各自实际方法与limits |

`aliases`里的c1/r1只在该JSON的独立演示运行有效，正文可显示为`〔c1〕/〔r1〕`。三份文件各自从1编号，不能直接合并成主线的一轮别名账本。点击别名用其ref解析源字段；不要用数组索引猜某颗星或某条规则的位置。

八字/紫微两种口径可得相同四柱/宫位；样例如实保留，不为制造视觉差异修改出生时刻。紫微time_basis列是本命结果，运限`unavailable`应显示未提供，不能补造流年。天府全书异表是计算层可选能力，当前样例默认iztro，不能按页面文字擅自替换生年四化。

Schema与原生输入、错误边界、完整别名生成规则见[chart_compute契约](../chart_compute.md)。JSON只用于开发模拟，不能自动保存为用户档案或作为模型已经解读过的内容。
