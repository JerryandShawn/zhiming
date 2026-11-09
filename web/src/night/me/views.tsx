import type { MemoryItem, PersonItem, ProfileItem, SymbolItem } from './types';

export type MeView =
  | { kind: 'profile-view' | 'profile-edit' | 'profile-delete'; item: ProfileItem }
  | { kind: 'memory-edit' | 'memory-stop' | 'memory-delete'; item: MemoryItem }
  | { kind: 'person'; item: PersonItem }
  | { kind: 'symbol-delete'; item: SymbolItem };
export type OpenMeView = (view: MeView, origin: HTMLElement) => void;
