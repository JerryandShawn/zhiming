import type { MemoryCommands } from '../chat/interactions/contracts';
import { createAboutMeStore } from './me/port';
import type { AboutMeMemoryReceipt, AboutMePort, AboutMeState } from './me/types';

export type AskReceipt = { status: 'accepted'; answer: string; request_id: string };
export type NightPort = {
  mode: 'local-demo';
  memory: MemoryCommands;
  aboutMe: AboutMePort;
  currentReceipts: () => AboutMeMemoryReceipt[];
  subscribe: (listener: () => void) => () => void;
  autoSaveCategories: ReadonlySet<string>;
  answer: (answer: string, requestId: string) => Promise<AskReceipt>;
};

// Replace this factory with an authenticated adapter only after the missing APIs are frozen.
// No HTTP client, credentials or persistent storage is reachable from this adapter.
export function createNightPort(seed?: AboutMeState): NightPort {
  const aboutMe = createAboutMeStore(seed);
  const answers = new Map<string, AskReceipt>();
  return {
    mode: 'local-demo',
    aboutMe,
    get autoSaveCategories() {
      return new Set(aboutMe.getSnapshot().autoSaveCategories);
    },
    memory: aboutMe.memory,
    currentReceipts: aboutMe.currentReceipts,
    subscribe: aboutMe.subscribe,
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
