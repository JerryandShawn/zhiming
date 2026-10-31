import { beforeEach, describe, expect, it } from 'vitest';
import { createDemoDataset } from '../src/spaces/fixtures';
import { applyProposal, getTopicStats, makeProposal, validateDataset } from '../src/spaces/proposal';
import { useSpacesDemo } from '../src/spaces/store';
import type { Dataset } from '../src/spaces/types';

const state = () => useSpacesDemo.getState();
const originals = (data: Dataset) => data.messages.map(({ id, text, at, role }) => ({ id, text, at, role }));

beforeEach(() => state().reset());

describe('功能区整理的本地模拟状态', () => {
  it('仅加载合成的七区，敏感区明确标记，引用完整', () => {
    const data = createDemoDataset();
    expect(data.spaces).toHaveLength(7);
    expect(data.spaces.filter((space) => space.sensitive).map((space) => space.name)).toEqual(['身心', '财务']);
    expect(data.topics.filter((topic) => topic.spaceId === 'career')).toHaveLength(2);
    expect(data.topics.find((topic) => topic.id === 'interview')!.messageIds).toHaveLength(4);
    expect(() => validateDataset(data)).not.toThrow();
  });

  it('改名和显式跨敏感区移动只更新草稿，应用后才改变归属', () => {
    const before = structuredClone(state().data);
    expect(state().renameSpace('career', '工作与学习')).toBe(true);
    expect(state().renameTopic('interview', '产品岗位准备')).toBe(true);
    expect(state().moveTopic('interview', 'finance')).toBe(true);
    expect(state().data).toEqual(before);
    expect(state().apply()).toBe(true);
    expect(state().data.spaces.find((space) => space.id === 'career')!.name).toBe('工作与学习');
    expect(
      state()
        .data.messages.filter((message) => message.topicId === 'interview')
        .every((message) => message.spaceId === 'finance'),
    ).toBe(true);
    expect(state().data.cases[0].spaceId).toBe('finance');
    expect(originals(state().data)).toEqual(originals(before));
    expect(() => validateDataset(state().data)).not.toThrow();
  });

  it('合并后更新关联事项，应用与撤销逐字段恢复整个数据集', () => {
    const before = structuredClone(state().data);
    expect(state().mergeTopics(['interview'], 'skills')).toBe(true);
    expect(state().draft.topics.find((topic) => topic.id === 'skills')!.messageIds).toHaveLength(6);
    expect(state().apply()).toBe(true);
    expect(state().applied!.batchId).toMatch(/^demo-/);
    expect(state().data.topics.some((topic) => topic.id === 'interview')).toBe(false);
    expect(state().data.cases[0].topicId).toBe('skills');
    expect(originals(state().data)).toEqual(originals(before));
    expect(state().revert()).toBe(true);
    expect(state().data).toEqual(before);
    expect(state().applied).toBeUndefined();
    expect(state().draft).toEqual(makeProposal(before));
  });

  it('只拆分选中的消息，新旧话题的数量和时间跨度来自原始记录', () => {
    const before = structuredClone(state().data);
    expect(state().splitTopic('interview', ['i3', 'i4'], '协作分歧练习')).toBe(true);
    const created = state().draft.topics.find((topic) => topic.title === '协作分歧练习')!;
    expect(created.messageIds).toEqual(['i3', 'i4']);
    expect(getTopicStats(created, before.messages)).toEqual({
      count: 2,
      start: before.messages.find((message) => message.id === 'i3')!.at,
      end: before.messages.find((message) => message.id === 'i4')!.at,
      sample: before.messages.find((message) => message.id === 'i3')!.text,
    });
    expect(state().apply()).toBe(true);
    expect(state().data.messages.find((message) => message.id === 'i3')!.topicId).toBe(created.id);
    expect(state().data.messages.find((message) => message.id === 'i1')!.topicId).toBe('interview');
    expect(originals(state().data)).toEqual(originals(before));
    expect(state().revert()).toBe(true);
    expect(state().data).toEqual(before);
  });

  it('忽略恢复原话题归属并排除本批，之后不能继续编辑该话题', () => {
    const before = structuredClone(state().data);
    state().renameTopic('interview', '不应写入的新名称');
    state().moveTopic('interview', 'wellbeing');
    expect(state().ignoreTopic('interview')).toBe(true);
    expect(state().draft.ignoredTopicIds).toEqual(['interview']);
    expect(state().renameTopic('interview', '再次修改')).toBe(false);
    expect(state().apply()).toBe(true);
    expect(state().data).toEqual(before);
  });

  it('合并后忽略目标话题也不丢弃其他来源消息，拆分后忽略可恢复原消息组', () => {
    const before = structuredClone(state().data);
    state().mergeTopics(['skills'], 'interview');
    expect(state().ignoreTopic('interview')).toBe(true);
    expect(state().apply()).toBe(true);
    expect(state().data.topics.find((topic) => topic.id === 'interview')).toEqual(
      before.topics.find((topic) => topic.id === 'interview'),
    );
    expect(originals(state().data)).toEqual(originals(before));
    expect(() => validateDataset(state().data)).not.toThrow();
    state().reset();
    state().splitTopic('interview', ['i3', 'i4'], '临时拆分');
    state().ignoreTopic('interview');
    state().apply();
    expect(state().data).toEqual(before);
  });

  it.each([
    ['空区名', () => state().renameSpace('career', '  ')],
    ['空话题名', () => state().renameTopic('interview', '')],
    ['不存在的区', () => state().moveTopic('interview', 'missing')],
    ['跨区合并', () => state().mergeTopics(['budget'], 'interview')],
    ['自己合并', () => state().mergeTopics(['interview'], 'interview')],
    ['空拆分', () => state().splitTopic('interview', [], '新话题')],
    ['全部拆分', () => state().splitTopic('interview', ['i1', 'i2', 'i3', 'i4'], '新话题')],
    ['重复消息拆分', () => state().splitTopic('interview', ['i1', 'i1'], '新话题')],
    ['其他话题消息拆分', () => state().splitTopic('interview', ['budget-1'], '新话题')],
  ])('%s被拒绝且不修改数据或草稿', (_label, action) => {
    const before = structuredClone(state().data);
    const draft = structuredClone(state().draft);
    expect(action()).toBe(false);
    expect(state().data).toEqual(before);
    expect(state().draft).toEqual(draft);
    expect(state().status).not.toBe('');
  });

  it('拒绝重复应用和应用后编辑，不产生另一个批次', () => {
    state().renameTopic('interview', '准备面试');
    state().apply();
    const batch = structuredClone(state().applied);
    const data = structuredClone(state().data);
    expect(state().apply()).toBe(false);
    expect(state().renameTopic('interview', '不应生效')).toBe(false);
    expect(state().resetDraft()).toBe(false);
    expect(state().applied).toEqual(batch);
    expect(state().data).toEqual(data);
  });

  it('手动归区可创建话题且只改变指定消息，不改写正文或时间', () => {
    const before = structuredClone(state().data);
    expect(state().routeMessage('i2', 'family', 'new', '安排下一步')).toBe(true);
    const message = state().data.messages.find((item) => item.id === 'i2')!;
    const topic = state().data.topics.find((item) => item.id === message.topicId)!;
    expect(topic.title).toBe('安排下一步');
    expect(topic.messageIds).toEqual(['i2']);
    expect(message.spaceId).toBe('family');
    const familyTopics = state().data.topics.filter((item) => item.spaceId === 'family');
    expect(state().data.spaces.find((space) => space.id === 'family')!.lastAt).toBe(
      familyTopics
        .map((item) => item.lastAt)
        .sort()
        .at(-1),
    );
    expect(state().data.messages.find((item) => item.id === 'i1')!.spaceId).toBe('career');
    expect(originals(state().data)).toEqual(originals(before));
    expect(() => validateDataset(state().data)).not.toThrow();
  });

  it('话题最后一条消息移走时迁移关联事项，保持无孤儿引用', () => {
    for (const id of ['i1', 'i2', 'i3', 'i4']) expect(state().routeMessage(id, 'finance', 'budget')).toBe(true);
    expect(state().data.topics.some((topic) => topic.id === 'interview')).toBe(false);
    expect(state().data.cases[0]).toMatchObject({ topicId: 'budget', spaceId: 'finance' });
    expect(state().data.spaces.find((space) => space.id === 'career')!.lastAt).toBe(
      state().data.topics.find((topic) => topic.id === 'skills')!.lastAt,
    );
    expect(() => validateDataset(state().data)).not.toThrow();
  });

  it('某区全部话题移走后清空最近活跃时间，不保留旧归属的时间', () => {
    expect(state().moveTopic('weekend', 'family')).toBe(true);
    expect(state().apply()).toBe(true);
    expect(state().data.spaces.find((space) => space.id === 'daily')!.lastAt).toBe('');
  });

  it('未应用草稿不会被消息归区静默覆盖，非法目标不会生成空话题', () => {
    state().renameTopic('interview', '已编辑');
    const data = structuredClone(state().data);
    const draft = structuredClone(state().draft);
    expect(state().routeMessage('i2', 'family', 'new', '家庭沟通')).toBe(false);
    expect(state().data).toEqual(data);
    expect(state().draft).toEqual(draft);
    state().resetDraft();
    expect(state().routeMessage('i2', 'family', 'new', '')).toBe(false);
    expect(state().routeMessage('i2', 'family', 'budget')).toBe(false);
    expect(state().data).toEqual(data);
  });

  it('应用后的新归区阻止撤销覆盖，保留新归区和批次供冲突说明', () => {
    state().renameTopic('interview', '已应用');
    state().apply();
    state().routeMessage('i2', 'family', 'new', '新归区');
    const latest = structuredClone(state().data);
    const batchId = state().applied!.batchId;
    expect(state().revert()).toBe(false);
    expect(state().status).toContain('避免覆盖');
    expect(state().data).toEqual(latest);
    expect(state().applied!.batchId).toBe(batchId);
  });

  it('重复选择原归属是无操作，不改变消息顺序，也不制造撤销冲突', () => {
    state().renameTopic('interview', '已应用');
    state().apply();
    const data = structuredClone(state().data);
    expect(state().routeMessage('i2', 'career', 'interview')).toBe(true);
    expect(state().data).toEqual(data);
    expect(state().revert()).toBe(true);
  });

  it('应用前重新校验消息唯一归属，损坏草稿不能写入', () => {
    const data = createDemoDataset();
    const draft = makeProposal(data);
    draft.topics[0].messageIds.push('i1');
    expect(() => applyProposal(data, draft)).toThrow('重复');
    draft.topics[0].messageIds.pop();
    draft.topics[1].messageIds.pop();
    expect(() => applyProposal(data, draft)).toThrow('不完整');
  });

  it('样例摘要限制为 80 个 Unicode 字符，统计按消息时间排序', () => {
    const data = createDemoDataset();
    const topic = data.topics.find((item) => item.id === 'interview')!;
    data.messages.find((item) => item.id === 'i1')!.text = '🌿'.repeat(100);
    const stats = getTopicStats(topic, [...data.messages].reverse());
    expect(Array.from(stats.sample)).toHaveLength(80);
    expect(stats.start).toBe(topic.createdAt);
    expect(stats.end).toBe(topic.lastAt);
  });
});
