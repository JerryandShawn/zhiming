import type { Receipt } from '../types';

export type MemoryAction = 'undo' | 'remember' | 'dismiss' | 'remember-category';
export type MemoryCommandReceipt = {
  write_status: 'saved' | 'stopped' | 'deleted' | 'dismissed';
  fact_id?: string;
  proposal_id?: string;
  summary?: string;
  revision?: number;
  undo_token?: string;
  category?: string;
  category_saved?: boolean;
};
export interface MemoryCommands {
  supports(action: MemoryAction, receipt: Receipt): boolean;
  execute(action: MemoryAction, receipt: Receipt): Promise<MemoryCommandReceipt>;
}
export type MemoryActionHandler = MemoryCommands['execute'];
export type AskAnswerReceipt = { status: 'accepted'; answer: string; request_id: string };
export type AskAnswerHandler = (answer: string) => Promise<AskAnswerReceipt>;

export function validMemoryReceipt(action: MemoryAction, source: Receipt, result: MemoryCommandReceipt) {
  const statuses =
    action === 'undo' ? ['stopped', 'deleted'] : action === 'dismiss' ? ['dismissed', 'stopped', 'deleted'] : ['saved'];
  if (!result || !statuses.includes(result.write_status)) return false;
  if (
    action === 'remember-category' &&
    (!source.category || result.category_saved !== true || (result.category && result.category !== source.category))
  )
    return false;
  if (
    source.fact_id &&
    result.fact_id === source.fact_id &&
    Number.isInteger(source.revision) &&
    Number.isInteger(result.revision) &&
    result.revision! < source.revision!
  )
    return false;
  if (source.proposal_id)
    return result.proposal_id === source.proposal_id && (result.write_status !== 'saved' || Boolean(result.fact_id));
  return Boolean(source.fact_id) && result.fact_id === source.fact_id;
}
