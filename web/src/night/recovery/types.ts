export type RecoveryPort = {
  runId: string;
  mode: 'memory' | 'local-fixture';
  connect: (lastEventId: string | undefined, signal: AbortSignal) => Promise<Response>;
};
export type RecoveryOptions = { rejectFirst?: boolean; delayMs?: number; now?: () => Date };
