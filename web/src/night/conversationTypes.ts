import type { StreamState } from '../chat/types';
import type { DemoScenario } from './events';

export type DemoJob = { id: string; scenario: DemoScenario; prompt: string; images: string[] };
export type DemoTurn = DemoJob & { state: StreamState; answered?: string; answeredOptionIds?: string[] };
export const INITIAL_DEMO_PROMPT = '有两个方向拿不定主意，想先理清怎么迈出第一步。';
