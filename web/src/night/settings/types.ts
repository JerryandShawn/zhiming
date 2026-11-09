import type { ReportKind, Schedule, Schedules } from '../../live/types';

export type ReportDraft = { enabled: boolean; time: string; weekday?: number; day?: number | 'last' };
export type ContactDraft = {
  followup: boolean;
  dailyCap: 1 | 2 | 3;
  dndStart: string;
  dndEnd: string;
  disabledCategories: string[];
};
export type ContactSettings = ContactDraft & { revision: number };
export type MockDevice = {
  id: string;
  label: string;
  current: boolean;
  lastUsedAt: string;
  revision: number;
  status: 'active' | 'revoked';
};
export type SettingsSnapshot = {
  mode: 'local-demo';
  revision: number;
  reports: Schedules;
  contact: ContactSettings;
  devices: MockDevice[];
  localSessionEnded: boolean;
};
export type SettingsCommand = { requestId: string } & (
  | { type: 'report-save'; kind: ReportKind; expectedRevision: number; draft: ReportDraft }
  | { type: 'contact-save'; expectedRevision: number; draft: ContactDraft }
  | { type: 'device-revoke'; id: string; expectedRevision: number }
  | { type: 'local-logout'; expectedRevision: number }
);
export type SettingsReceipt = {
  requestId: string;
  kind: SettingsCommand['type'];
  write_status: 'saved' | 'revoked';
  revision: number;
  snapshotRevision: number;
  report?: Schedule;
  contact?: ContactSettings;
  device?: MockDevice;
};
export type OnboardingContactPreference = { requestId: string; choice: 'allow' | 'off' | 'custom-time'; time?: string };
export type ContactPreferenceProjection = {
  revision: number;
  followup: boolean;
  dailyEnabled: boolean;
  time: string;
  dailyCap: 1 | 2 | 3;
  dndStart: string;
  dndEnd: string;
  local: true;
};
export type ContactPreferenceReceipt = {
  requestId: string;
  kind: 'contact-preference';
  write_status: 'saved';
  revision: number;
  projection: ContactPreferenceProjection;
};
export type SettingsPort = {
  getSnapshot: () => SettingsSnapshot;
  subscribe: (listener: () => void) => () => void;
  execute: (command: SettingsCommand) => Promise<SettingsReceipt>;
  applyContactPreference: (preference: OnboardingContactPreference) => Promise<ContactPreferenceReceipt>;
  readContactPreference: () => ContactPreferenceProjection;
};
