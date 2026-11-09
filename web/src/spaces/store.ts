import { create } from 'zustand';
import { createDemoDataset } from './fixtures';
import {
  applyProposal,
  clone,
  ignoreOriginal,
  makeProposal,
  refreshSpaces,
  refreshTopic,
  validateDataset,
  validateProposal,
} from './proposal';
import type { AppliedBatch, Dataset, Proposal, Topic } from './types';

interface SpacesDemoState {
  data: Dataset;
  draft: Proposal;
  applied?: AppliedBatch;
  status: string;
  renameSpace: (id: string, name: string) => boolean;
  renameTopic: (id: string, title: string) => boolean;
  moveTopic: (id: string, spaceId: string) => boolean;
  mergeTopics: (sourceIds: string[], targetId: string) => boolean;
  splitTopic: (id: string, messageIds: string[], title: string) => boolean;
  ignoreTopic: (id: string) => boolean;
  resetDraft: () => boolean;
  apply: () => boolean;
  revert: () => boolean;
  routeMessage: (messageId: string, spaceId: string, topicId: string, title?: string) => boolean;
  reset: () => void;
}

const initialData = createDemoDataset();
function named(value: string, label: string) {
  const result = value.trim();
  if (!result) throw new Error(`${label}不能为空。`);
  if (Array.from(result).length > 60) throw new Error(`${label}请控制在 60 字以内。`);
  return result;
}

function editable(draft: Proposal, id: string): Topic {
  if (draft.ignoredTopicIds.includes(id)) throw new Error('该话题已忽略，请重置建议后再编辑。');
  const topic = draft.topics.find((item) => item.id === id);
  if (!topic) throw new Error('话题不存在，请重新选择。');
  return topic;
}

export const useSpacesDemo = create<SpacesDemoState>((set, get) => {
  const failure = (error: unknown) => {
    set({ status: error instanceof Error ? error.message : '模拟操作未完成。' });
    return false;
  };
  const edit = (mutate: (draft: Proposal) => void, status: string) => {
    const state = get();
    if (state.applied) return failure(new Error('本批已应用，请先撤销再编辑建议。'));
    try {
      const draft = clone(state.draft);
      mutate(draft);
      validateProposal(draft, state.data);
      set({ draft, status });
      return true;
    } catch (error) {
      return failure(error);
    }
  };
  return {
    data: clone(initialData),
    draft: makeProposal(initialData),
    applied: undefined,
    status: '合成示例，仅在当前页面内存中保留；刷新后重置。',
    renameSpace: (id, name) =>
      edit((draft) => {
        const space = draft.spaces.find((item) => item.id === id);
        if (!space) throw new Error('功能区不存在。');
        space.name = named(name, '区名称');
      }, '已修改区名，尚未应用。'),
    renameTopic: (id, title) =>
      edit((draft) => {
        editable(draft, id).title = named(title, '话题名称');
      }, '已修改话题名，尚未应用。'),
    moveTopic: (id, spaceId) =>
      edit((draft) => {
        if (!draft.spaces.some((space) => space.id === spaceId)) throw new Error('目标功能区不存在。');
        editable(draft, id).spaceId = spaceId;
      }, '已修改话题归区，尚未应用。'),
    mergeTopics: (sourceIds, targetId) =>
      edit((draft) => {
        const target = editable(draft, targetId);
        const ids = [...new Set(sourceIds)];
        if (!ids.length || ids.includes(targetId)) throw new Error('请选择不同的来源话题和目标话题。');
        const sources = ids.map((id) => editable(draft, id));
        if (sources.some((topic) => topic.spaceId !== target.spaceId))
          throw new Error('请先移动到同一个区，再合并话题。');
        target.messageIds.push(...sources.flatMap((topic) => topic.messageIds));
        target.messageIds.sort((a, b) => {
          const messages = get().data.messages;
          return (
            Date.parse(messages.find((message) => message.id === a)!.at) -
            Date.parse(messages.find((message) => message.id === b)!.at)
          );
        });
        refreshTopic(target, get().data.messages);
        draft.topics = draft.topics.filter((topic) => !ids.includes(topic.id));
      }, '已合并话题建议，原始消息保持不变；尚未应用。'),
    splitTopic: (id, messageIds, title) =>
      edit((draft) => {
        const topic = editable(draft, id);
        const ids = new Set(messageIds);
        if (!ids.size || ids.size >= topic.messageIds.length)
          throw new Error('请选择部分消息拆分，原话题至少保留一条。');
        if (ids.size !== messageIds.length || messageIds.some((messageId) => !topic.messageIds.includes(messageId)))
          throw new Error('所选消息无效或重复。');
        const created = {
          ...clone(topic),
          id: `topic-${crypto.randomUUID()}`,
          title: named(title, '话题名称'),
          messageIds: topic.messageIds.filter((messageId) => ids.has(messageId)),
        };
        topic.messageIds = topic.messageIds.filter((messageId) => !ids.has(messageId));
        refreshTopic(topic, get().data.messages);
        refreshTopic(created, get().data.messages);
        draft.topics.push(created);
      }, '已拆分话题建议，原始消息保持不变；尚未应用。'),
    ignoreTopic: (id) =>
      edit((draft) => {
        ignoreOriginal(draft, get().data, id);
      }, '本批已忽略该话题，保留原归属；相关的其他消息独立保留。'),
    resetDraft: () => {
      if (get().applied) return failure(new Error('本批已应用，请先撤销再重置建议。'));
      set({ draft: makeProposal(get().data), status: '建议已重置，未更改已存消息。' });
      return true;
    },
    apply: () => {
      const state = get();
      if (state.applied) return failure(new Error('本批已经应用，请勿重复提交。'));
      try {
        const data = applyProposal(state.data, state.draft);
        const applied = { batchId: `demo-${crypto.randomUUID()}`, before: clone(state.data), after: clone(data) };
        set({ data, applied, status: `模拟整理已应用，批次 ${applied.batchId}；没有写入服务器。` });
        return true;
      } catch (error) {
        return failure(error);
      }
    },
    revert: () => {
      const state = get();
      if (!state.applied) return failure(new Error('当前没有可撤销的模拟批次。'));
      if (JSON.stringify(state.data) !== JSON.stringify(state.applied.after))
        return failure(new Error('应用后存在新的归区修改；为避免覆盖，本批不能直接撤销。请重置合成示例后继续。'));
      const data = clone(state.applied.before);
      set({
        data,
        draft: makeProposal(data),
        applied: undefined,
        status: '模拟批次已撤销，数据已逐字段恢复；没有写入服务器。',
      });
      return true;
    },
    routeMessage: (messageId, spaceId, topicId, title) => {
      const state = get();
      try {
        const data = clone(state.data);
        if (!data.spaces.some((space) => space.id === spaceId)) throw new Error('目标功能区不存在。');
        const message = data.messages.find((item) => item.id === messageId);
        if (!message) throw new Error('消息不存在。');
        if (message.spaceId === spaceId && message.topicId === topicId) {
          set({ status: '这条消息已在所选话题中，归属没有改变。' });
          return true;
        }
        let topic = data.topics.find((item) => item.id === topicId && item.spaceId === spaceId);
        if (topicId === 'new') {
          topic = {
            id: `topic-${crypto.randomUUID()}`,
            spaceId,
            title: named(title ?? '', '新话题名称'),
            status: 'open',
            summary: '合成示例：手动建立的话题。',
            messageIds: [],
            createdAt: message.at,
            lastAt: message.at,
          };
          data.topics.push(topic);
        }
        if (!topic) throw new Error('请选择该区中的话题。');
        for (const current of data.topics) current.messageIds = current.messageIds.filter((id) => id !== messageId);
        topic.messageIds.push(messageId);
        const times = new Map(data.messages.map((item) => [item.id, Date.parse(item.at)]));
        topic.messageIds.sort((a, b) => times.get(a)! - times.get(b)!);
        message.spaceId = spaceId;
        message.topicId = topic.id;
        data.topics = data.topics.filter((current) => current.messageIds.length);
        for (const current of data.topics) refreshTopic(current, data.messages);
        const existing = new Set(data.topics.map((current) => current.id));
        data.memories = data.memories.map((item) =>
          item.topicId && !existing.has(item.topicId) ? { ...item, topicId: topic.id, spaceId } : item,
        );
        data.cases = data.cases.map((item) =>
          item.topicId && !existing.has(item.topicId) ? { ...item, topicId: topic.id, spaceId } : item,
        );
        refreshSpaces(data, state.data);
        validateDataset(data);
        const draftChanged = JSON.stringify(state.draft) !== JSON.stringify(makeProposal(state.data));
        if (!state.applied && draftChanged) throw new Error('请先重置或应用整理建议，再手动修改消息归区。');
        set({
          data,
          ...(state.applied ? {} : { draft: makeProposal(data) }),
          status: '模拟归区已修改；消息原文与时间保持不变，没有写入服务器。',
        });
        return true;
      } catch (error) {
        return failure(error);
      }
    },
    reset: () => {
      const data = createDemoDataset();
      set({ data, draft: makeProposal(data), applied: undefined, status: '合成示例已重置；没有读取或修改真实数据。' });
    },
  };
});
