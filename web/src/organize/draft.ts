import { OrganizeError, type EditIntent, type OrganizeSeed, type ReviewSegment, type ReviewTopic } from './types';
import { identity, validateDocument } from './values';

export function validateSeed(seed: OrganizeSeed) {
  identity(seed.batch_id);
  validateDocument(seed.document, seed.document.owner_id, seed.document.subject_id);
  const spaces = new Set(seed.spaces.map((item) => item.id));
  if (!spaces.size || spaces.size !== seed.spaces.length) throw new OrganizeError('INVALID', '功能区目录无效。');
  for (const space of seed.spaces) identity(space.id);
  const messages = seed.segments.flatMap((item) => item.message_ids);
  if (
    new Set(messages).size !== messages.length ||
    messages.length !== Object.keys(seed.document.messages).length ||
    messages.some((id) => !Object.hasOwn(seed.document.messages, id))
  )
    throw new OrganizeError('INVALID', '片段消息归属不完整。');
  if (
    new Set(seed.topics.map((item) => item.id)).size !== seed.topics.length ||
    new Set(seed.segments.map((item) => item.id)).size !== seed.segments.length
  )
    throw new OrganizeError('INVALID', '话题或片段标识重复。');
  for (const topic of seed.topics) {
    identity(topic.id);
    title(topic.title);
    if (!spaces.has(topic.space_id) || Object.hasOwn(seed.document.topics, topic.id))
      throw new OrganizeError('INVALID', '建议话题归区无效或标识已被占用。');
    const linked = seed.segments.filter((item) => item.topic_id === topic.id);
    if (
      new Set(topic.segment_ids).size !== topic.segment_ids.length ||
      new Set(topic.message_ids).size !== topic.message_ids.length ||
      topic.segment_ids.length !== linked.length ||
      topic.segment_ids.some((id) => !linked.some((item) => item.id === id)) ||
      topic.message_ids.length !== linked.reduce((count, item) => count + item.message_ids.length, 0)
    )
      throw new OrganizeError('INVALID', '话题与片段目录不一致。');
  }
  for (const segment of seed.segments) {
    identity(segment.id);
    const topic = seed.topics.find((item) => item.id === segment.topic_id);
    if (
      !topic ||
      !topic.segment_ids.includes(segment.id) ||
      !segment.message_ids.length ||
      segment.message_ids.some((id) => !topic.message_ids.includes(id)) ||
      !Number.isFinite(segment.confidence) ||
      segment.confidence < 0 ||
      segment.confidence > 1 ||
      !['pending', 'accepted', 'rejected'].includes(segment.decision)
    )
      throw new OrganizeError('INVALID', '片段建议格式无效。');
  }
}
function title(value: string) {
  if (typeof value !== 'string' || !value.trim() || Array.from(value.trim()).length > 80)
    throw new OrganizeError('INVALID', '话题名应为1至80字。');
  return value.trim();
}
export function editDraft(seed: OrganizeSeed, intent: EditIntent): OrganizeSeed {
  if (
    !intent ||
    !['accept', 'reject', 'move_segment', 'move_topic', 'rename_topic', 'merge_topics'].includes(intent.kind)
  )
    throw new OrganizeError('INVALID', '整理操作类型无效。');
  const next = structuredClone(seed);
  const topic = (id: string) => {
    const item = next.topics.find((row) => row.id === id);
    if (!item) throw new OrganizeError('INVALID', '话题已变化，请重新选择。');
    return item;
  };
  const segment = (id: string) => {
    const item = next.segments.find((row) => row.id === id);
    if (!item) throw new OrganizeError('INVALID', '片段已变化，请重新选择。');
    return item;
  };
  if (intent.kind === 'accept' || intent.kind === 'reject')
    segment(intent.segment_id).decision = intent.kind === 'accept' ? 'accepted' : 'rejected';
  if (intent.kind === 'rename_topic') topic(intent.topic_id).title = title(intent.title);
  if (intent.kind === 'move_topic') {
    if (!next.spaces.some((item) => item.id === intent.space_id)) throw new OrganizeError('INVALID', '目标区不存在。');
    topic(intent.topic_id).space_id = intent.space_id;
  }
  if (intent.kind === 'move_segment') {
    const item = segment(intent.segment_id),
      target = topic(intent.target_topic_id);
    item.topic_id = target.id;
  }
  if (intent.kind === 'merge_topics') merge(next.topics, next.segments, intent);
  refreshTopics(next);
  validateSeed(next);
  return next;
}
function merge(
  topics: ReviewTopic[],
  segments: ReviewSegment[],
  intent: Extract<EditIntent, { kind: 'merge_topics' }>,
) {
  if (new Set(intent.topic_ids).size !== intent.topic_ids.length)
    throw new OrganizeError('INVALID', '合并话题不能重复。');
  const ids = new Set([...intent.topic_ids, intent.target_topic_id]);
  const target = topics.find((item) => item.id === intent.target_topic_id);
  const selected = topics.filter((item) => ids.has(item.id));
  if (
    !target ||
    ids.size < 2 ||
    selected.length !== ids.size ||
    selected.some((item) => item.space_id !== target.space_id)
  )
    throw new OrganizeError('INVALID', '请先把至少两个不同话题移到同一区，再合并。');
  if (intent.title !== undefined) target.title = title(intent.title);
  for (const item of segments) if (ids.has(item.topic_id)) item.topic_id = target.id;
}
function refreshTopics(seed: OrganizeSeed) {
  seed.topics = seed.topics.filter((item) => seed.segments.some((segment) => segment.topic_id === item.id));
  for (const topic of seed.topics) {
    const segments = seed.segments.filter((item) => item.topic_id === topic.id);
    topic.segment_ids = segments.map((item) => item.id);
    topic.message_ids = segments
      .flatMap((item) => item.message_ids)
      .sort((a, b) => seed.document.messages[a].at_ms - seed.document.messages[b].at_ms);
  }
}
