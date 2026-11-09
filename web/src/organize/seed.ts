import type { MessageRecord, OrganizeSeed, SpaceChoice } from './types';

export const ORGANIZE_SPACES: SpaceChoice[] = [
  { id: 'daily', name: '日常', sensitive: false },
  { id: 'career', name: '事业学业', sensitive: false },
  { id: 'relationships', name: '感情人际', sensitive: false },
  { id: 'family', name: '家庭', sensitive: false },
  { id: 'wellbeing', name: '身心', sensitive: true },
  { id: 'finance', name: '财务', sensitive: true },
  { id: 'metaphysics', name: '命理研习', sensitive: false },
];
const samples = [
  ['daily', '周末留白', '想在周末留一段散步的时间。'],
  ['career', '面试准备', '想练习怎样把项目经过说清楚。'],
  ['career', '学习安排', '想每周固定两晚学习新技能。'],
  ['relationships', '朋友相处', '和朋友约好一起看展，想先核对时间。'],
  ['family', '家庭聚餐', '想找一个大家都方便的聚餐日期。'],
  ['wellbeing', '休息节奏', '想记录作息，观察白天的精神变化。'],
  ['finance', '月度清单', '想把固定支出列成清单，再留出缓冲。'],
  ['metaphysics', '术语笔记', '想把宫位和十神的学习笔记整理一下。'],
] as const;

export function createOrganizeSeed(): OrganizeSeed {
  const owner_id = 'synthetic-organize-owner',
    subject_id = 'synthetic-organize-subject';
  const messages: Record<string, MessageRecord> = {};
  const segments = samples.map(([space, , text], index) => {
    const id = `segment-${index + 1}`,
      message = `message-${index + 1}`;
    const at_ms = Date.parse(`2026-10-${String(10 + index).padStart(2, '0')}T09:00:00+08:00`);
    messages[message] = {
      id: message,
      owner_id,
      subject_id,
      content: text,
      at_ms,
      role: 'user',
      revision: 1,
      status: 'active',
      space_id: 'daily',
      topic_id: 'legacy-all',
      retention_scope: 'persistent',
    };
    return {
      id,
      topic_id: `proposal-${index + 1}`,
      message_ids: [message],
      start: at_ms,
      end: at_ms,
      sample: text,
      confidence: space === 'daily' ? 0.35 : 0.88,
      needs_review: space === 'daily',
      decision: 'pending' as const,
    };
  });
  return {
    batch_id: 'synthetic-organize-20261021',
    document: {
      owner_id,
      subject_id,
      messages,
      topics: {
        'legacy-all': {
          id: 'legacy-all',
          owner_id,
          subject_id,
          title: '旧对话（合成）',
          space_id: 'daily',
          status: 'open',
          revision: 1,
          message_ids: Object.keys(messages),
        },
      },
    },
    spaces: structuredClone(ORGANIZE_SPACES),
    segments,
    topics: samples.map(([space_id, title], index) => ({
      id: `proposal-${index + 1}`,
      space_id,
      title,
      segment_ids: [`segment-${index + 1}`],
      message_ids: [`message-${index + 1}`],
    })),
  };
}
