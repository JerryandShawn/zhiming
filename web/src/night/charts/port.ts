import samples from './samples.json';
import type { ChartExample, ChartTab } from './types';

function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
// default_synthetic: local P8 engine output. This projection omits all request/profile/raw birth fields.
// Each source retains its own hash; sample aliases are intentionally not imported or merged.
export const chartSamples: Record<ChartTab, ChartExample> = freeze(samples);
export function readChartExample(tab: ChartTab): ChartExample {
  return chartSamples[tab];
}
