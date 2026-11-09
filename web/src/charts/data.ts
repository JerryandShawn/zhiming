export type ChartRecord = Record<string, unknown>;
export const object = (value: unknown): ChartRecord =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as ChartRecord) : {};
export const list = (value: unknown): ChartRecord[] => (Array.isArray(value) ? value.map(object) : []);
export const label = (value: unknown) => (typeof value === 'string' || typeof value === 'number' ? String(value) : '');
export const number = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;
export const longitude = (value: unknown): number | null => {
  const result = number(value);
  return result !== null && result >= 0 && result <= 360 ? result % 360 : null;
};
export const signs = ['白羊', '金牛', '双子', '巨蟹', '狮子', '处女', '天秤', '天蝎', '射手', '摩羯', '水瓶', '双鱼'];
export const positionLabel = (value: number) => `${signs[Math.floor(value / 30)]} ${(value % 30).toFixed(2)}°`;
export function wheelPoint(value: number, radius: number, ascendant = 0) {
  const angle = ((ascendant - value + 180) * Math.PI) / 180;
  return { x: 200 + Math.cos(angle) * radius, y: 200 + Math.sin(angle) * radius };
}
export const palacePositions: Record<string, readonly [number, number]> = {
  巳: [1, 1],
  午: [2, 1],
  未: [3, 1],
  申: [4, 1],
  酉: [4, 2],
  戌: [4, 3],
  亥: [4, 4],
  子: [3, 4],
  丑: [2, 4],
  寅: [1, 4],
  卯: [1, 3],
  辰: [1, 2],
};
