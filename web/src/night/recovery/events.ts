import { beijingTimestamp, systemClock } from '../../time/beijing';

export const RECOVERY_RUN_ID = 'synthetic-recovery';
export const RECOVERY_OLD_TEXT = '恢复前的重复旧片段。';
export const RECOVERY_RESET_TEXT = '恢复后的正文已经替换重复片段。';
export const RECOVERY_DELTA_TEXT = '接着从这里继续。';
const factId = 'synthetic-recovery-memory';
const receipt = { fact_id: factId, write_status: 'undone', summary: '合成偏好已撤销', sensitive: false };

export function recoveryChunks(resuming: boolean, now: () => Date = systemClock.now): string[] {
  const event = (seq: number, type: string, body: Record<string, unknown>) =>
    `id: ${seq}\r\nevent: ${type}\r\ndata: ${JSON.stringify({ v: 1, run_id: RECOVERY_RUN_ID, seq, ts: beijingTimestamp(now()), ...body })}\r\n\r\n`;
  if (!resuming)
    return [
      ': ping\r\n\r\n' +
        event(1, 'started', {
          thread_id: 'synthetic-recovery-thread',
          message_id: 'synthetic-recovery-message',
          incognito: false,
        }),
      event(2, 'text_delta', { text: RECOVERY_OLD_TEXT }),
      event(3, 'memory_receipt', receipt),
      event(4, 'text_reset', {
        text: '这个残帧不能进入正文。',
        reason: 'resumed',
        revision_id: 'synthetic-partial',
        // A lone CR also terminates an SSE line; remove the entire blank separator.
      }).slice(0, -2),
    ];
  return [
    event(3, 'memory_receipt', receipt),
    event(4, 'text_reset', { text: RECOVERY_RESET_TEXT, reason: 'resumed', revision_id: 'synthetic-resumed-1' }),
    event(5, 'text_delta', { text: RECOVERY_DELTA_TEXT }),
    event(6, 'final', {
      message_id: 'synthetic-recovery-message',
      envelope: {
        schema: 'core4.0',
        message_id: 'synthetic-recovery-message',
        text: RECOVERY_RESET_TEXT + RECOVERY_DELTA_TEXT,
        receipts: [{ fact_id: factId, write_status: 'undone' }],
        used_fact_ids: [],
        used_claim_ids: [],
        asked: null,
        options: null,
        review: { state: 'passed', reasons: [] },
        usage: { offline: true },
      },
    }),
  ];
}
