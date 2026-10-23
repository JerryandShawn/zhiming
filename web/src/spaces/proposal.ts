import type { Dataset, Proposal, SpaceMessage, Topic } from './types';

export function clone<T>(value: T): T {
  return structuredClone(value);
}

export function makeProposal(data: Dataset): Proposal {
  return { spaces: clone(data.spaces), topics: clone(data.topics), ignoredTopicIds: [] };
}

export function getTopicStats(topic: Topic, messages: SpaceMessage[]) {
  const ids = new Set(topic.messageIds);
  const rows = messages.filter((message) => ids.has(message.id)).sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  return {
    count: rows.length,
    start: rows[0]?.at ?? '',
    end: rows.at(-1)?.at ?? '',
    sample: Array.from(rows[0]?.text ?? '')
      .slice(0, 80)
      .join(''),
  };
}

export function refreshTopic(topic: Topic, messages: SpaceMessage[]) {
  const stats = getTopicStats(topic, messages);
  topic.createdAt = stats.start;
  topic.lastAt = stats.end;
}

export function refreshSpaces(data: Dataset, previous: Dataset) {
  for (const space of data.spaces) {
    space.lastAt =
      data.topics
        .filter((topic) => topic.spaceId === space.id)
        .map((topic) => topic.lastAt)
        .sort((a, b) => Date.parse(a) - Date.parse(b))
        .at(-1) ?? '';
    const original = previous.spaces.find((candidate) => candidate.id === space.id);
    if (original && JSON.stringify(space) !== JSON.stringify(original)) space.revision = original.revision + 1;
  }
}

function unique(values: string[], description: string) {
  if (new Set(values).size !== values.length) throw new Error(`${description}存在重复项。`);
}

export function validateProposal(draft: Proposal, data: Dataset) {
  unique(
    draft.spaces.map((space) => space.id),
    '功能区',
  );
  unique(
    draft.topics.map((topic) => topic.id),
    '话题',
  );
  const spaces = new Set(draft.spaces.map((space) => space.id));
  const messageIds = draft.topics.flatMap((topic) => topic.messageIds);
  unique(messageIds, '消息归属');
  const expected = new Set(data.messages.map((message) => message.id));
  if (messageIds.length !== expected.size || messageIds.some((id) => !expected.has(id))) {
    throw new Error('消息归属不完整，未应用任何改动。');
  }
  if (draft.spaces.some((space) => !space.name.trim())) throw new Error('区名称不能为空。');
  for (const topic of draft.topics) {
    if (!spaces.has(topic.spaceId)) throw new Error('话题必须归入存在的功能区。');
    if (!topic.title.trim()) throw new Error('话题名称不能为空。');
    if (!topic.messageIds.length) throw new Error('话题至少保留一条消息。');
  }
}

export function validateDataset(data: Dataset) {
  validateProposal(makeProposal(data), data);
  unique(
    data.messages.map((message) => message.id),
    '原始消息',
  );
  const spaces = new Set(data.spaces.map((space) => space.id));
  const topics = new Map(data.topics.map((topic) => [topic.id, topic]));
  for (const message of data.messages) {
    const topic = topics.get(message.topicId);
    if (!topic?.messageIds.includes(message.id) || topic.spaceId !== message.spaceId)
      throw new Error('消息与话题归属不一致。');
    if (message.secondarySpaceId && !spaces.has(message.secondarySpaceId)) throw new Error('消息副区不存在。');
  }
  for (const item of [...data.memories, ...data.cases]) {
    if (!spaces.has(item.spaceId)) throw new Error('关联记录的功能区不存在。');
    if (item.topicId && topics.get(item.topicId)?.spaceId !== item.spaceId)
      throw new Error('关联记录的话题不存在或归区不一致。');
  }
  if (data.people.some((person) => !spaces.has(person.spaceId))) throw new Error('人物归区不存在。');
}

export function applyProposal(data: Dataset, draft: Proposal): Dataset {
  validateProposal(draft, data);
  const next = clone(data);
  next.spaces = clone(draft.spaces);
  next.topics = clone(draft.topics);
  const owners = new Map(next.topics.flatMap((topic) => topic.messageIds.map((id) => [id, topic] as const)));
  next.messages = next.messages.map((message) => ({
    ...message,
    topicId: owners.get(message.id)!.id,
    spaceId: owners.get(message.id)!.spaceId,
  }));
  const relatedTopic = (id?: string) => {
    if (!id) return undefined;
    return (
      next.topics.find((topic) => topic.id === id) ??
      owners.get(data.topics.find((topic) => topic.id === id)?.messageIds[0] ?? '')
    );
  };
  next.memories = next.memories.map((memory) => {
    const topic = relatedTopic(memory.topicId);
    return topic ? { ...memory, topicId: topic.id, spaceId: topic.spaceId } : memory;
  });
  next.cases = next.cases.map((item) => {
    const topic = relatedTopic(item.topicId);
    return topic ? { ...item, topicId: topic.id, spaceId: topic.spaceId } : item;
  });
  refreshSpaces(next, data);
  validateDataset(next);
  return next;
}

export function ignoreOriginal(draft: Proposal, data: Dataset, id: string) {
  const original = data.topics.find((topic) => topic.id === id);
  if (!original) throw new Error('新拆出的话题没有原始归属，请重置建议后再忽略原话题。');
  const ids = new Set(original.messageIds);
  draft.topics = draft.topics.flatMap((topic) => {
    const remaining = topic.messageIds.filter((messageId) => !ids.has(messageId));
    if (!remaining.length) return [];
    const next = { ...topic, messageIds: remaining };
    if (topic.id === id) next.id = `topic-${crypto.randomUUID()}`;
    refreshTopic(next, data.messages);
    return [next];
  });
  draft.topics.push(clone(original));
  const order = new Map(data.topics.map((topic, index) => [topic.id, index]));
  draft.topics.sort(
    (a, b) => (order.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.id) ?? Number.MAX_SAFE_INTEGER),
  );
  draft.ignoredTopicIds = [...new Set([...draft.ignoredTopicIds, id])];
}
