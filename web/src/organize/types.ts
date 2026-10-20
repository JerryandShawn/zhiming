export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Collection = 'messages' | 'topics';
export type FieldValue = { present: false } | { present: true; value: Json };
export type FieldKey = { collection: Collection; entity_id: string; field: string | null };
export type FieldChange = FieldKey & { before: FieldValue; after: FieldValue };
export type SourceGuard = { collection: Collection; entity_id: string; immutable_digest: string };

// Actual module ChangeSet.as_dict shape, audited at v4/mod-organize@8c554bd.
export type WireChangeSet = {
  batch_id: string;
  owner_id: string;
  subject_id: string;
  ops: FieldChange[];
  inverse_ops: FieldChange[];
  source_guards: SourceGuard[];
};
export type MessageRecord = {
  id: string;
  owner_id: string;
  subject_id: string;
  content: string;
  at_ms: number;
  role: 'user' | 'assistant';
  revision: number;
  status: string;
  incognito?: boolean;
  thread_id?: string;
  retention_scope?: string;
  deleted_at?: string | null;
  revoked_at?: string | null;
  source_status?: string;
  space_id?: string | null;
  topic_id?: string | null;
  space_secondary?: string | null;
  route_source?: string;
  route_confidence?: number;
};
export type TopicRecord = {
  id: string;
  owner_id: string;
  subject_id: string;
  title: string;
  space_id: string;
  status: string;
  message_ids: string[];
  revision?: number;
  deleted_at?: string | null;
  revoked_at?: string | null;
};
export type OrganizeDocument = {
  owner_id: string;
  subject_id: string;
  messages: Record<string, MessageRecord>;
  topics: Record<string, TopicRecord>;
};
export type SpaceChoice = { id: string; name: string; sensitive: boolean };
export type ReviewTopic = { id: string; space_id: string; title: string; segment_ids: string[]; message_ids: string[] };
export type ReviewSegment = {
  id: string;
  topic_id: string;
  message_ids: string[];
  start: number;
  end: number;
  sample: string;
  confidence: number;
  needs_review: boolean;
  decision: 'pending' | 'accepted' | 'rejected';
  source_available?: boolean;
};
export type OrganizeSeed = {
  batch_id: string;
  document: OrganizeDocument;
  spaces: SpaceChoice[];
  topics: ReviewTopic[];
  segments: ReviewSegment[];
};
export type EditIntent =
  | { kind: 'accept' | 'reject'; segment_id: string }
  | { kind: 'move_segment'; segment_id: string; target_topic_id: string }
  | { kind: 'move_topic'; topic_id: string; space_id: string }
  | { kind: 'rename_topic'; topic_id: string; title: string }
  | { kind: 'merge_topics'; topic_ids: string[]; target_topic_id: string; title?: string };
export type EditCommand = { request_id: string; expected_revision: number; intent: EditIntent };
export type CommandReceipt = {
  status: 'accepted' | 'rejected';
  request_id: string;
  revision: number;
  code?: string;
  message: string;
};
export type ConfirmationScope = { action: 'apply' | 'revert'; fields?: FieldKey[] };
export type ConfirmationTicket = ConfirmationScope & {
  id: string;
  batch_id: string;
  owner_id: string;
  subject_id: string;
  revision: number;
  issued_at_ms: number;
  expires_at_ms: number;
};
export type AppliedField = FieldChange & {
  state: 'applied' | 'reverted' | 'conflict';
  group_id: string;
  label: string;
};
export type RevertConflict = FieldKey & { batch_id: string; reason: 'field_changed' | 'later_references' };
export type OrganizeSummary = {
  accepted_segments: number;
  rejected_segments: number;
  pending_segments: number;
  message_count: number;
  field_changes: number;
  topic_creations: number;
};
export type OrganizeSnapshot = {
  revision: number;
  status: 'draft' | 'applied' | 'partially_reverted' | 'reverted';
  spaces: SpaceChoice[];
  topics: ReviewTopic[];
  segments: ReviewSegment[];
  document: OrganizeDocument;
  summary: OrganizeSummary;
  changeset: WireChangeSet | null;
  applied?: { batch_id: string; fields: AppliedField[] };
  conflicts: RevertConflict[];
  metadata: { module_sha: string; mode: 'synthetic'; encoder_mode: string; degradation: string };
};
export interface OrganizePort {
  getSnapshot(): OrganizeSnapshot;
  subscribe(listener: () => void): () => void;
  edit(command: EditCommand): Promise<CommandReceipt>;
  prepareConfirmation(scope: ConfirmationScope): ConfirmationTicket;
  execute(command: { request_id: string; ticket_id: string }): Promise<CommandReceipt>;
  refresh(document: OrganizeDocument): void;
}
export type OrganizeOptions = {
  now?: () => number;
  seed?: OrganizeSeed;
  digest?: (canonicalJson: string) => Promise<string>;
  nonce?: () => string;
};
export class OrganizeError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = 'OrganizeError';
  }
}
