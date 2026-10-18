import type { ChartRecord } from '../../charts/data';

export type ChartTab = 'bazi' | 'ziwei' | 'astro';
export type ChartExample = { data: ChartRecord; basis: ChartRecord; sourceSha256: string };
