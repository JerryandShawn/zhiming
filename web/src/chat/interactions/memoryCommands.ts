import { write } from '../../api/operations';
import type { Receipt } from '../types';
import type { MemoryCommands, MemoryCommandReceipt } from './contracts';

type V3Receipt = { id?: string; fact_id?: string; status?: string; write_status?: string; revision?: number };
export const v3MemoryCommands: MemoryCommands = {
  supports: (action, receipt) =>
    action === 'undo' &&
    receipt.write_status === 'saved' &&
    Boolean(receipt.fact_id) &&
    Number.isInteger(receipt.revision),
  async execute(action, receipt: Receipt): Promise<MemoryCommandReceipt> {
    if (!v3MemoryCommands.supports(action, receipt)) throw new Error('此操作尚未接入，记忆状态没有改变');
    const result = await write<V3Receipt>(
      `chat-undo:${receipt.fact_id}`,
      'PATCH',
      `/api/memories/${encodeURIComponent(receipt.fact_id!)}`,
      {
        expected_revision: receipt.revision,
        status: 'hidden',
      },
      {
        receipt: (value) =>
          (value.write_status === 'stopped' || value.status === 'hidden') &&
          (!value.id || value.id === receipt.fact_id) &&
          (!value.fact_id || value.fact_id === receipt.fact_id),
      },
    );
    return {
      fact_id: result.fact_id || result.id || receipt.fact_id,
      write_status: 'stopped',
      revision: result.revision,
    };
  },
};
