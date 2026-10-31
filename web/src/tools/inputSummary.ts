import { kindLabels, sampleNames } from './port';
import type { SynastryQuery, WindowQuery } from './types';
import type { QuerySummary } from './inputValidationTypes';

export function windowInputSummary(query: WindowQuery, dayCount: number): QuerySummary {
  return [
    { id: 'purpose', label: '用途', value: query.purpose },
    { id: 'range', label: '日期区间（北京时间）', value: `${query.startDate} 至 ${query.endDate}` },
    { id: 'days', label: '含起止日期', value: `${dayCount}天` },
    { id: 'pagination', label: '请求分页', value: `偏移${query.offset}，每页最多${query.limit}天` },
  ];
}

export function synastryInputSummary(query: SynastryQuery): QuerySummary {
  return [
    { id: 'a', label: 'A方', value: sampleNames[query.a] },
    { id: 'b', label: 'B方', value: sampleNames[query.b] },
    { id: 'kind', label: '比较用途', value: kindLabels[query.kind] },
    { id: 'asOfDate', label: '核对日期（北京时间）', value: query.asOfDate },
    { id: 'orbDegrees', label: '统一相位容许度', value: `${query.orbDegrees}°` },
  ];
}
