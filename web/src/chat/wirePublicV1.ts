import { bounded, identifier, ids, integer, keys, optional, optionalId, record, text } from './wireChecksV1';
export type WirePublicReceiptV1 = {
  write_status: string;
  id?: string | null;
  fact_id?: string | null;
  proposal_id?: string | null;
  draw_id?: string | null;
  kind?: string | null;
  revision?: number | null;
  status?: string | null;
  code?: string | null;
  affected_ids?: string[];
};
export type WireTokenUsageV1 = {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
  cache_read_input_tokens?: number | null;
};
export type WirePublicUsageV1 = {
  model_steps?: number | null;
  model_streams_this_execution?: number | null;
  replayed_model_steps?: number | null;
  reported_tokens?: WireTokenUsageV1;
  usage_known?: boolean;
  offline?: boolean | null;
};
export type WireValidationV1 = { status: 'validated'; valid: true; schema: 'core4.0' };
export type WirePublicMetaV1 = {
  core_run: { run_id: string; operation_id: string };
  subject_id: string;
  case_ids: string[];
  structural_warnings: { code: string; count: number }[];
};
export function isWirePublicReceiptV1(value: unknown): value is WirePublicReceiptV1 {
  return (
    record(value) &&
    keys(
      value,
      ['write_status'],
      ['id', 'fact_id', 'proposal_id', 'draw_id', 'kind', 'revision', 'status', 'code', 'affected_ids'],
    ) &&
    text(value.write_status) &&
    ['id', 'fact_id', 'proposal_id', 'draw_id'].every((key) => optionalId(value, key)) &&
    ['kind', 'status', 'code'].every((key) => optional(value, key, text)) &&
    optional(value, 'revision', (v) => integer(v, 1)) &&
    (!Object.hasOwn(value, 'affected_ids') || ids(value.affected_ids, 1024))
  );
}
export function isWireUsageV1(value: unknown): value is WirePublicUsageV1 {
  if (
    !record(value) ||
    !keys(
      value,
      [],
      [
        'model_steps',
        'model_streams_this_execution',
        'replayed_model_steps',
        'reported_tokens',
        'usage_known',
        'offline',
      ],
    )
  )
    return false;
  const tokenKeys = ['input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'];
  return (
    ['model_steps', 'model_streams_this_execution', 'replayed_model_steps'].every((key) =>
      optional(value, key, (v) => integer(v, 0)),
    ) &&
    (!Object.hasOwn(value, 'usage_known') || typeof value.usage_known === 'boolean') &&
    optional(value, 'offline', (v) => typeof v === 'boolean') &&
    (!Object.hasOwn(value, 'reported_tokens') ||
      (record(value.reported_tokens) &&
        keys(value.reported_tokens, [], tokenKeys) &&
        tokenKeys.every((key) =>
          optional(value.reported_tokens as Record<string, unknown>, key, (v) => integer(v, 0)),
        )))
  );
}
export function isWireValidationV1(value: unknown): value is WireValidationV1 {
  return (
    record(value) &&
    keys(value, ['status', 'valid', 'schema']) &&
    value.status === 'validated' &&
    value.valid === true &&
    value.schema === 'core4.0'
  );
}
export function isWireMetaV1(value: unknown): value is WirePublicMetaV1 {
  return (
    record(value) &&
    keys(value, ['core_run', 'subject_id', 'case_ids', 'structural_warnings']) &&
    record(value.core_run) &&
    keys(value.core_run, ['run_id', 'operation_id']) &&
    identifier(value.core_run.run_id) &&
    identifier(value.core_run.operation_id) &&
    identifier(value.subject_id) &&
    ids(value.case_ids) &&
    Array.isArray(value.structural_warnings) &&
    value.structural_warnings.every(
      (item) => record(item) && keys(item, ['code', 'count']) && bounded(item.code, Infinity) && integer(item.count, 1),
    )
  );
}
