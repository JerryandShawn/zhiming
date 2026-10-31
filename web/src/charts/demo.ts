import type { ChartRecord } from './data';

// Independent, explicitly synthetic fixtures; these are not calculated personal charts.
const branches = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
const names = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'];
const stars = ['紫微', '天府', '太阴', '天机', '天梁', '天同', '廉贞', '武曲', '太阳', '巨门', '贪狼', '七杀'];
export const ziweiDemo: ChartRecord = {
  ming_gong: '子',
  shen_gong: '午',
  wuxing_ju: '水二局 · 合成示例',
  palaces: branches.map((branch, index) => ({
    index,
    name: names[index],
    ganzhi: ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸', '甲', '乙'][index] + branch,
    is_body: index === 6,
    major:
      index === 3
        ? []
        : [
            {
              name: stars[index],
              brightness: index % 2 ? '旺' : '庙',
              ...(index < 4 ? { mutagen: ['禄', '权', '科', '忌'][index] } : {}),
            },
          ],
    minor: [{ name: index % 2 ? '文昌' : '左辅', ...(index === 3 ? { mutagen: '忌' } : {}) }],
    linked_palaces: [4, 8, 6].map((offset) => ({
      relation: offset === 6 ? '对宫' : '三合',
      name: names[(index + offset) % 12],
      ganzhi: '甲' + branches[(index + offset) % 12],
    })),
  })),
};
const angles: Record<string, number> = {
  太阳: 15,
  月亮: 105,
  水星: 17,
  金星: 225,
  火星: 282,
  木星: 135,
  土星: 46,
  天王: 78,
  海王: 348,
  冥王: 302,
};
export const astroDemo: ChartRecord = {
  asc: { longitude: 0 },
  planets: Object.fromEntries(
    Object.entries(angles).map(([name, value], index) => [
      name,
      { longitude: value, house: Math.floor(value / 30) + 1, retrograde: index === 6 },
    ]),
  ),
  houses: Array.from({ length: 12 }, (_, index) => ({ house: index + 1, longitude: index * 30 })),
  aspects: [
    { from: '太阳', to: '水星', aspect: '合相', angle: 0, orb: 2 },
    { from: '太阳', to: '月亮', aspect: '刑相', angle: 90, orb: 0 },
    { from: '太阳', to: '木星', aspect: '拱相', angle: 120, orb: 0 },
    { from: '月亮', to: '金星', aspect: '拱相', angle: 120, orb: 0 },
    { from: '木星', to: '金星', aspect: '刑相', angle: 90, orb: 0 },
  ],
};
export const baziDemo: ChartRecord = {
  dayun: ['戊辰', '己巳', '庚午', '辛未', '壬申', '癸酉'].map((ganzhi, index) => ({
    ganzhi,
    start_age: 9 + index * 10,
    start_year: 2002 + index * 10,
    end_year: 2011 + index * 10,
    ten_god: ['伤官', '食神', '正财', '偏财', '正官', '七杀'][index],
  })),
};
const pillars = (hour: string) =>
  Object.fromEntries(
    ['year', 'month', 'day', 'hour'].map((key, index) => [key, { ganzhi: ['甲戌', '丁卯', '丁酉', hour][index] }]),
  );
export const timeBasisDemo: ChartRecord = {
  time_basis: { selected_basis: 'true_solar', requires_confirmation: false },
  interpretation: {
    primary_chart_ids: ['demo:true_solar'],
    physical_instant_confirmation_required: false,
    comparisons: [
      {
        primary_chart_id: 'demo:true_solar',
        comparison_chart_id: 'demo:beijing_standard',
        fields_changed: ['bazi.pillars.hour', 'ziwei.ming_gong'],
      },
    ],
  },
  charts: [
    {
      id: 'demo:true_solar',
      time_basis: { basis: 'true_solar', instant_id: 'demo' },
      data: { pillars: pillars('甲辰') },
      ziwei_column: { ming_gong: '子', shen_gong: '午' },
    },
    {
      id: 'demo:beijing_standard',
      time_basis: { basis: 'beijing_standard', instant_id: 'demo' },
      data: { pillars: pillars('乙巳') },
      ziwei_column: { ming_gong: '丑', shen_gong: '未' },
    },
  ],
};
