import type { AskAnswerContext, AskAnswerReceipt, MemoryCommands } from '../chat/interactions/contracts';
import type { Receipt } from '../chat/types';
import { createAboutMeStore } from './me/port';
import type { AboutMeMemoryReceipt, AboutMePort, AboutMeState } from './me/types';

export type AskReceipt = AskAnswerReceipt;
export type NightPort = {
  mode: 'local-demo';
  memory: MemoryCommands;
  aboutMe: AboutMePort;
  currentReceipts: () => AboutMeMemoryReceipt[];
  subscribe: (listener: () => void) => () => void;
  autoSaveCategories: ReadonlySet<string>;
  answer: (answer: string, requestId: string, context?: AskAnswerContext) => Promise<AskReceipt>;
};

// Replace this factory with an authenticated adapter only after the missing APIs are frozen.
// No HTTP client, credentials or persistent storage is reachable from this adapter.
export function createNightPort(seed?: AboutMeState): NightPort {
  const aboutMe = createAboutMeStore(seed);
  const answers = new Map<string, { signature: string; result: AskReceipt }>();
  const wireSources = new Map<string, Receipt>();
  function commandSource(item: Receipt): Receipt {
    if (typeof item.sensitive !== 'boolean') return item;
    const key = JSON.stringify(item);
    const bound = wireSources.get(key);
    if (bound) return bound;
    const current = aboutMe
      .currentReceipts()
      .find((candidate) =>
        item.fact_id ? candidate.fact_id === item.fact_id : candidate.proposal_id === item.proposal_id,
      );
    // v1 carries public consent state; the isolated aggregate supplies its own CAS revision.
    const source = {
      ...item,
      write_status: item.write_status === 'pending_confirm' ? 'pending_confirmation' : item.write_status,
      ...(current && current.summary === item.summary
        ? { revision: item.revision ?? current.revision, category: item.category ?? current.category }
        : {}),
    };
    if (current && current.summary === item.summary) wireSources.set(key, source);
    return source;
  }
  // Both views expose the same adapter and still write the one authoritative local aggregate.
  const memory: MemoryCommands = {
    supports: (action, item) => aboutMe.memory.supports(action, commandSource(item)),
    execute: (action, item) => aboutMe.memory.execute(action, commandSource(item)),
  };
  return {
    mode: 'local-demo',
    aboutMe: { ...aboutMe, memory },
    get autoSaveCategories() {
      return new Set(aboutMe.getSnapshot().autoSaveCategories);
    },
    memory,
    currentReceipts: aboutMe.currentReceipts,
    subscribe: aboutMe.subscribe,
    async answer(answer, requestId, context) {
      const signature = JSON.stringify([answer.trim(), context?.askId, context?.optionIds]);
      const previous = answers.get(requestId);
      if (previous) {
        if (previous.signature !== signature) throw new Error('这一轮已经回答过了，请开启新的对话。');
        return previous.result;
      }
      if (!answer.trim()) throw new Error('先说说你的想法。');
      const result: AskReceipt = {
        status: 'accepted',
        answer: answer.trim(),
        request_id: requestId,
        ...(context ? { askId: context.askId, optionIds: [...context.optionIds] } : {}),
      };
      if (result.optionIds) Object.freeze(result.optionIds);
      Object.freeze(result);
      answers.set(requestId, { signature, result });
      return result;
    },
  };
}
