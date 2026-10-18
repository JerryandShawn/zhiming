import type { Receipt } from '../chat/types';
import type { MemoryAction, MemoryCommandReceipt, MemoryCommands } from '../chat/interactions/contracts';

export type AskReceipt = { status: 'accepted'; answer: string; request_id: string };
export type NightPort = {
  mode: 'local-demo';
  memory: MemoryCommands;
  autoSaveCategories: ReadonlySet<string>;
  answer: (answer: string, requestId: string) => Promise<AskReceipt>;
};

// Replace this factory with an authenticated adapter only after the missing APIs are frozen.
// No HTTP client, credentials or persistent storage is reachable from this adapter.
export function createNightPort(): NightPort {
  const completed = new Map<string, { fingerprint: string; result: MemoryCommandReceipt }>();
  const answers = new Map<string, AskReceipt>();
  const current = new Map<string, Receipt>();
  const autoSaveCategories = new Set<string>();
  function supports(action: MemoryAction, item: Receipt) {
    if (action === 'undo') return item.write_status === 'saved' && Boolean(item.fact_id);
    return (
      item.write_status === 'pending_confirmation' &&
      Boolean(item.proposal_id) &&
      (action !== 'remember-category' || Boolean(item.category))
    );
  }
  return {
    mode: 'local-demo',
    autoSaveCategories,
    memory: {
      supports,
      async execute(action, item) {
        const id = item.fact_id || item.proposal_id || '';
        const key = `${action}:${id}:${item.revision ?? 0}`;
        const fingerprint = JSON.stringify({
          action,
          fact: item.fact_id,
          proposal: item.proposal_id,
          revision: item.revision,
          status: item.write_status,
          summary: item.summary,
          category: item.category,
        });
        const previous = completed.get(key);
        if (previous) {
          if (previous.fingerprint !== fingerprint) throw new Error('原操作的内容已经改变，请重新确认。');
          return previous.result;
        }
        if (!supports(action, item)) throw new Error('这条演示记录目前不能进行这个操作。');
        const latest = current.get(id);
        if (latest && (latest.revision !== item.revision || latest.write_status !== item.write_status))
          throw new Error('这条记录已变化，请重新查看后再操作。');
        const result: MemoryCommandReceipt = {
          write_status: action === 'undo' ? 'stopped' : action === 'dismiss' ? 'dismissed' : 'saved',
          fact_id: action === 'dismiss' ? undefined : item.fact_id || `local-fact-${id}`,
          proposal_id: item.proposal_id,
          summary: item.summary,
          revision: (item.revision ?? 0) + 1,
          category_saved: action === 'remember-category',
          category: item.category,
        };
        if (action === 'remember-category' && item.category) autoSaveCategories.add(item.category);
        completed.set(key, { fingerprint, result });
        current.set(id, { ...item, ...result, summary: result.summary || item.summary });
        if (result.fact_id) current.set(result.fact_id, { ...item, ...result, summary: item.summary });
        return result;
      },
    },
    async answer(answer, requestId) {
      const previous = answers.get(requestId);
      if (previous) {
        if (previous.answer !== answer.trim()) throw new Error('这一轮已经回答过了，请开启新的对话。');
        return previous;
      }
      if (!answer.trim()) throw new Error('先说说你的想法。');
      const result: AskReceipt = { status: 'accepted', answer: answer.trim(), request_id: requestId };
      answers.set(requestId, result);
      return result;
    },
  };
}
