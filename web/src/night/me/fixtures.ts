import { PROFILE_SECTIONS, type AboutMeState, type MemoryItem, type SourceRecord, type SourceRef } from './types';

const at = '2026-10-19T03:00:00+08:00';
export function sourceRef(source: SourceRecord, quote: string): SourceRef {
  const position = source.content.indexOf(quote);
  if (position < 0) throw new Error('合成来源节选不存在。');
  const start = Array.from(source.content.slice(0, position)).length;
  return {
    messageId: source.id,
    version: source.revision,
    start,
    end: start + Array.from(quote).length,
    quote,
    at: source.at,
    channel: source.channel,
  };
}
function source(id: string, content: string, channel = 'feishu'): SourceRecord {
  return { id, revision: 1, content, at, channel, role: 'user', status: 'active' };
}
const entries = [
  ['memory-basic', 'basic', '请叫我阿远，目前在学习产品设计。', 'source-intro', 'basic', 'career'],
  ['memory-life', 'current_life', '最近在准备产品岗位面试。', 'source-intro', 'career', 'career'],
  ['memory-goals', 'goals', '希望工作之外也留一点自己的时间。', 'source-goals', 'goals', 'career'],
  ['memory-people', 'people', '小林是常一起看展的朋友。', 'source-people', 'relationship', 'relationships'],
  [
    'memory-boundaries',
    'preferences',
    '不喜欢被催着决定，想留一点独处时间。',
    'source-boundaries',
    'preference',
    'daily',
  ],
  ['local-preference', 'communication', '偏好先看简短结论（合成示例）', 'source-preference', 'communication', 'daily'],
  [
    'memory-chart',
    'chart_summary',
    '合成命理档案：象征解读仅作文化参考，口径与可信度仍需核对。',
    'source-chart',
    'study',
    'study',
  ],
  ['memory-followup', 'followups', '下周面试后想回顾准备过程。', 'source-followup', 'plan', 'career'],
] as const;

export function createAboutMeSeed(): AboutMeState {
  const sources = [
    source(
      'source-intro',
      '请叫我阿远，目前在学习产品设计。最近在准备产品岗位面试。希望先确认再记这次面试的安排。这句未授权节选不应整段展示',
    ),
    source('source-goals', '希望工作之外也留一点自己的时间。'),
    source('source-people', '小林是常一起看展的朋友。'),
    source('source-boundaries', '不喜欢被催着决定，想留一点独处时间。'),
    source('source-preference', '我喜欢先看简短结论，再看依据。这句未授权节选不应整段展示'),
    source('source-chart', '合成命理档案：象征解读仅作文化参考，口径与可信度仍需核对。'),
    source('source-followup', '下周面试后想回顾准备过程。'),
    source('source-health', '希望跟进一项健康安排（合成示例）'),
    source('source-symbol', '星星对我来说是慢一点也没关系。'),
  ];
  const ref = (id: string, quote: string) =>
    sourceRef(
      sources.find((item) => item.id === id)!,
      quote,
    );
  const memories: MemoryItem[] = entries.map(([id, , text, sourceId, category, spaceId]) => ({
    id,
    text,
    category,
    spaceId,
    revision: 1,
    status: 'active',
    createdAt: at,
    updatedAt: at,
    sourceRefs: [ref(sourceId, id === 'local-preference' ? '我喜欢先看简短结论，再看依据。' : text)],
    ...(id === 'memory-people' ? { personId: 'person-lin' } : {}),
    ...(id === 'memory-followup' ? { eventAt: '2026-10-21T18:00:00+08:00' } : {}),
  }));
  return {
    revision: 1,
    sources,
    memories,
    revokedFactIds: [],
    profileItems: entries.map(([factId, section, text]) => {
      const memory = memories.find((item) => item.id === factId)!;
      return {
        id: `profile-${section}`,
        section,
        text,
        revision: 1,
        updatedAt: at,
        sourceIds: memory.sourceRefs.map((item) => item.messageId),
        factIds: [factId],
        sourceRefs: memory.sourceRefs,
        confidence: 1,
        pinned: false,
        userEdited: false,
        status: 'active',
      };
    }),
    proposals: [
      {
        id: 'local-proposal',
        text: '希望跟进一项健康安排（合成示例）',
        revision: 1,
        status: 'pending',
        category: 'health',
        kind: 'sensitive',
        sourceRefs: [ref('source-health', '希望跟进一项健康安排（合成示例）')],
        createdAt: at,
        updatedAt: at,
      },
      {
        id: 'local-proposal-career',
        text: '希望先确认再记这次面试的安排。',
        revision: 1,
        status: 'pending',
        category: 'career',
        kind: 'sensitive',
        sourceRefs: [ref('source-intro', '希望先确认再记这次面试的安排。')],
        createdAt: at,
        updatedAt: at,
      },
      {
        id: 'legacy-note',
        text: '旧版候选：喜欢给计划留出缓冲。',
        revision: 1,
        status: 'pending',
        kind: 'legacy-note',
        sourceRefs: [],
        createdAt: at,
        updatedAt: at,
      },
    ],
    people: [{ id: 'person-lin', name: '小林（合成人物）', relation: '朋友', memoryIds: ['memory-people'] }],
    timeline: [
      {
        id: 'timeline-interview',
        text: '面试后回顾准备过程',
        at: '2026-10-21T18:00:00+08:00',
        memoryIds: ['memory-followup'],
        sourceRefs: memories[7].sourceRefs,
      },
    ],
    dictionary: [
      {
        id: 'symbol-star',
        symbol: '星星',
        text: '慢一点也没关系',
        revision: 1,
        status: 'active',
        sourceRefs: [ref('source-symbol', '星星对我来说是慢一点也没关系。')],
      },
    ],
    autoSaveCategories: [],
    lastOrganizedAt: at,
  };
}

// Every section exists in the UI even when its profileItems array is empty.
export const sectionIds = PROFILE_SECTIONS.map((section) => section.id);
