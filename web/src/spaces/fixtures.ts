import type { Dataset, SpaceMessage } from './types';

const definitions = [
  ['daily', '日常', '闲聊、心情与暂时无法归类的近况', false],
  ['career', '事业学业', '工作、学习与能力成长', false],
  ['relationships', '感情人际', '朋友、伴侣与同事的相处', false],
  ['family', '家庭', '亲人、家务与家庭安排', false],
  ['wellbeing', '身心', '身体、情绪与休息', true],
  ['finance', '财务', '收支与财务安排', true],
  ['study', '命理研习', '命盘、知识学习与研习笔记', false],
] as const;

const conversations = [
  ['daily', 'weekend', '周末散步', '想在周末去公园走走。', '可以先留一段不用赶时间的空白。'],
  ['career', 'interview', '跳槽 · 面试', '下周有一场产品岗位面试。', '先准备一个你能讲清楚过程与结果的项目例子。'],
  ['career', 'skills', '学习计划', '想每周留两晚学习数据分析。', '可以从一份小数据集开始，每周完成一个问题。'],
  ['relationships', 'friends', '朋友相处', '和朋友约了下周一起看展。', '提前核对好时间，给彼此留出余地。'],
  ['family', 'reunion', '家庭聚餐', '想在月底安排一次家庭聚餐。', '先收集大家方便的日期，再一起确定地点。'],
  ['wellbeing', 'sleep', '休息节奏', '最近想把入睡时间往前挪半小时。', '先记录一周作息，观察白天精神有没有变化。'],
  ['finance', 'budget', '月度预算', '准备把每月固定支出列成清单。', '先区分必需与可调整的项目，再留出缓冲。'],
  ['study', 'chart-study', '我的命盘', '想把命盘里常见的术语整理成笔记。', '可以逐条记录含义、依据和仍待验证的部分。'],
] as const;

export function createDemoDataset(): Dataset {
  const messages: SpaceMessage[] = [];
  const topics = conversations.map(([spaceId, id, title, question, answer], index) => {
    const prefix = id === 'interview' ? 'i' : `${id}-`;
    const date = `2026-10-${String(10 + index).padStart(2, '0')}`;
    const pair: SpaceMessage[] = [
      { id: `${prefix}1`, spaceId, topicId: id, role: 'user', text: question, at: `${date}T09:00:00+08:00` },
      { id: `${prefix}2`, spaceId, topicId: id, role: 'assistant', text: answer, at: `${date}T09:01:00+08:00` },
    ];
    if (id === 'interview') {
      pair.push(
        {
          id: 'i3',
          spaceId,
          topicId: id,
          role: 'user',
          text: '我还想练习如何回答协作中的分歧。',
          at: `${date}T09:03:00+08:00`,
        },
        {
          id: 'i4',
          spaceId,
          topicId: id,
          role: 'assistant',
          text: '选一个具体分歧，说明你听到了什么、怎样达成下一步。',
          at: `${date}T09:04:00+08:00`,
        },
      );
    }
    messages.push(...pair);
    return {
      id,
      spaceId,
      title,
      status: id === 'interview' ? ('case' as const) : ('open' as const),
      summary: `合成示例：${question}`,
      messageIds: pair.map((message) => message.id),
      createdAt: pair[0].at,
      lastAt: pair.at(-1)!.at,
      needsReview: id === 'weekend',
    };
  });
  return {
    spaces: definitions.map(([id, name, description, sensitive], order) => ({
      id,
      name,
      description,
      sensitive,
      order,
      hidden: false,
      revision: 1,
      lastAt: topics.filter((topic) => topic.spaceId === id).at(-1)!.lastAt,
      unread: id === 'career' ? 2 : 0,
    })),
    topics,
    messages,
    memories: definitions.map(([spaceId, name]) => ({
      id: `memory-${spaceId}`,
      spaceId,
      text: `合成示例：愿意定期整理${name}的近况。`,
    })),
    people: [
      { id: 'person-friend', spaceId: 'relationships', name: '小林（合成人物）', relation: '朋友' },
      { id: 'person-family', spaceId: 'family', name: '家人甲（合成人物）', relation: '家人' },
    ],
    cases: [
      {
        id: 'case-interview',
        spaceId: 'career',
        topicId: 'interview',
        title: '准备产品岗位面试（合成事项）',
        status: '进行中',
      },
    ],
  };
}

export const DEMO_DATASET = createDemoDataset();
