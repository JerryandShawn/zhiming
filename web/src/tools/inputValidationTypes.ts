import type { SynastryQuery, WindowQuery } from './types';

export type WindowField = keyof WindowQuery;
export type SynastryField = keyof SynastryQuery;
export type InputIssueCode =
  | 'invalid-shape'
  | 'required'
  | 'invalid-choice'
  | 'invalid-date'
  | 'date-out-of-range'
  | 'range-order'
  | 'range-too-long'
  | 'invalid-offset'
  | 'invalid-limit'
  | 'same-object'
  | 'invalid-orb';
export type FieldIssue<Field extends string> = {
  field: Field | 'query';
  code: InputIssueCode;
  message: string;
};
export type QuerySummary = readonly { id: string; label: string; value: string }[];
export type InvalidInput<Field extends string> = { status: 'invalid'; issues: FieldIssue<Field>[] };
export type ValidInput<Query> = {
  status: 'valid';
  query: Query;
  summary: QuerySummary;
  coverage: 'query-fields-only';
};
export type InputValidation<Query, Field extends string> = InvalidInput<Field> | ValidInput<Query>;
export type UnavailableInput<Query> = Omit<ValidInput<Query>, 'status'> & {
  status: 'unavailable';
  code: 'sample-unavailable';
  message: string;
};
