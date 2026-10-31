import type { StudySystem } from './types';

export const systemLabels: Record<StudySystem, string> = {
  bazi: '八字',
  ziwei: '紫微斗数',
  astro: '西方占星',
  tarot: '塔罗',
};
export const kindLabels = {
  orientation: '先学读法',
  matched_condition: '核对一项条件',
  boundary: '核对口径交界',
} as const;
export const basisLabels = {
  true_solar: '真太阳时口径',
  standard: '标准口径',
  beijing_standard: '北京时间口径',
  actual_UTC: '实际时刻坐标',
} as const;
