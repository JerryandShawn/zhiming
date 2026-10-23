import type { Receipt } from '../../chat/types';
import type { MemoryAction, MemoryCommands } from '../../chat/interactions/contracts';

export const PROFILE_SECTIONS = [
  { id: 'basic', label: '称呼与基本情况' },
  { id: 'current_life', label: '现在的生活' },
  { id: 'goals', label: '在意的事与目标' },
  { id: 'people', label: '重要的人' },
  { id: 'preferences', label: '偏好与禁忌' },
  { id: 'communication', label: '沟通偏好' },
  { id: 'chart_summary', label: '命理档案摘要' },
  { id: 'followups', label: '正在跟进' },
] as const;
export type ProfileSection = (typeof PROFILE_SECTIONS)[number]['id'];
export type SourceRef = {
  messageId: string;
  version: number;
  start: number;
  end: number;
  quote: string;
  at: string;
  channel: string;
};
export type ProfileItem = {
  id: string;
  section: ProfileSection;
  text: string;
  revision: number;
  updatedAt: string;
  sourceIds: string[];
  factIds: string[];
  sourceRefs: SourceRef[];
  confidence: number;
  pinned: boolean;
  userEdited: boolean;
  status: 'active' | 'deleted';
};
export type MemoryItem = {
  id: string;
  text: string;
  revision: number;
  status: 'active' | 'stopped' | 'deleted';
  category?: string;
  sourceRefs: SourceRef[];
  createdAt: string;
  updatedAt: string;
  spaceId?: string;
  personId?: string;
  eventAt?: string;
  proposalId?: string;
  categorySaved?: boolean;
};
export type ProposalItem = {
  id: string;
  text: string;
  revision: number;
  status: 'pending' | 'saved' | 'dismissed' | 'deleted';
  category?: string;
  sourceRefs: SourceRef[];
  createdAt: string;
  updatedAt: string;
  kind: 'sensitive' | 'legacy-note';
  factId?: string;
  categorySaved?: boolean;
};
export type PersonItem = { id: string; name: string; relation: string; memoryIds: string[] };
export type TimelineItem = { id: string; text: string; at: string; memoryIds: string[]; sourceRefs: SourceRef[] };
export type SymbolItem = {
  id: string;
  symbol: string;
  text: string;
  revision: number;
  status: 'active' | 'deleted';
  sourceRefs: SourceRef[];
};
export type SourceProjection = {
  ref: SourceRef;
  available: boolean;
  label?: string;
  quote?: string;
  reason?: string;
};
export type AboutMeMemoryReceipt = Receipt & { category_saved?: boolean };
export type AboutMeSnapshot = {
  revision: number;
  profileItems: ProfileItem[];
  memories: MemoryItem[];
  proposals: ProposalItem[];
  people: PersonItem[];
  timeline: TimelineItem[];
  dictionary: SymbolItem[];
  autoSaveCategories: string[];
  lastOrganizedAt: string;
};
export type DeleteScope = 'fact' | 'source';
export type DeletePreview = {
  scope: DeleteScope;
  targetId: string;
  snapshotRevision: number;
  targetRevision: number;
  sourceRef?: SourceRef;
  affectedFactIds: string[];
  affectedProfileIds: string[];
  affectedProposalIds: string[];
  affectedSymbolIds: string[];
  counts: { memories: number; profileItems: number; proposals: number; symbols: number };
};
type Versioned = { id: string; expectedRevision: number; requestId: string };
export type AboutMeCommand = Versioned &
  (
    | { type: 'profile-edit'; text: string; section?: ProfileSection }
    | { type: 'profile-delete' }
    | { type: 'memory-edit'; text: string }
    | { type: 'memory-stop' }
    | { type: 'memory-delete'; scope: DeleteScope; expectedSnapshotRevision: number; sourceRef?: SourceRef }
    | { type: 'proposal-act'; action: Exclude<MemoryAction, 'undo'> }
    | { type: 'symbol-delete' }
  );
export type AboutMeReceipt = {
  requestId: string;
  kind: AboutMeCommand['type'];
  write_status: 'saved' | 'stopped' | 'deleted' | 'dismissed';
  id: string;
  revision: number;
  snapshotRevision: number;
  factId?: string;
  sourceId?: string;
  affectedIds: string[];
  memoryReceipt?: AboutMeMemoryReceipt;
};
export type AboutMeErrorCode = 'CONFLICT' | 'INVALID' | 'NOT_FOUND' | 'REPLAY_CHANGED' | 'NETWORK' | 'RATE_LIMIT';
export class AboutMeError extends Error {
  constructor(
    public code: AboutMeErrorCode,
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'AboutMeError';
  }
}
export type AboutMePort = {
  getSnapshot: () => AboutMeSnapshot;
  subscribe: (listener: () => void) => () => void;
  readSource: (ref: SourceRef) => SourceProjection;
  previewDelete: (factId: string, scope: DeleteScope, sourceRef?: SourceRef) => DeletePreview;
  execute: (command: AboutMeCommand) => Promise<AboutMeReceipt>;
  currentReceipts: () => AboutMeMemoryReceipt[];
  memory: MemoryCommands;
};
// Source bodies are private to the mock aggregate, never part of its public snapshot.
export type SourceRecord = {
  id: string;
  revision: number;
  content: string;
  at: string;
  channel: string;
  role: 'user';
  status: 'active' | 'deleted';
};
export type AboutMeState = AboutMeSnapshot & { sources: SourceRecord[]; revokedFactIds: string[] };
export type ModelContext = { at: string; newId: (kind: string) => string };
