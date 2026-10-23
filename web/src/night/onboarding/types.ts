import type { AboutMePort } from '../me/types';
import type {
  OnboardingContactPreference,
  ContactPreferenceProjection,
  ContactPreferenceReceipt,
} from '../settings/types';

export type BirthDraft = {
  date: string;
  time: string;
  precision: '' | 'exact' | 'approximate' | 'unknown';
  uncertaintyMinutes: string;
  gender: '' | '男' | '女';
  city: string;
  longitude: string;
  latitude: string;
  timezoneOffset: string;
};
export type BirthSummary = {
  revision: number;
  status: 'unconfirmed' | 'partial' | 'complete';
  confirmedFields: (keyof BirthDraft)[];
  canComputeGift: false;
};
export type BirthReceipt = {
  requestId: string;
  kind: 'birth-confirm';
  write_status: 'saved';
  revision: number;
  confirmation: 'partial' | 'complete';
  confirmedFields: (keyof BirthDraft)[];
};
export type BirthCommand = { requestId: string; expectedRevision: number; confirmed: true; draft: BirthDraft };
export type BirthPort = {
  readSummary: () => BirthSummary;
  readPrivate: () => { revision: number; draft: BirthDraft };
  confirm: (command: BirthCommand) => Promise<BirthReceipt>;
};
export type OnboardingStep =
  | 'welcome'
  | 'user_name'
  | 'assistant_name'
  | 'birth'
  | 'current_life'
  | 'priorities'
  | 'directness'
  | 'terminology'
  | 'answer_length'
  | 'outreach'
  | 'outreach_time'
  | 'summary'
  | 'done';
export type OnboardingKnown = Partial<
  Record<Exclude<OnboardingStep, 'welcome' | 'summary' | 'done' | 'outreach_time'>, boolean>
>;
export type OnboardingMessage = { id: string; role: 'user' | 'assistant'; text: string };
export type OnboardingPrompt = { text: string; why: string; options: string[] };
export type OnboardingSnapshot = {
  sessionId: string;
  generation: number;
  stage: number;
  step: OnboardingStep;
  status: 'idle' | 'active' | 'paused' | 'complete';
  busy: boolean;
  hasPending: boolean;
  draft: string;
  prompt: OnboardingPrompt;
  messages: OnboardingMessage[];
  error?: string;
  conflicted: boolean;
};
export type OnboardingController = {
  getSnapshot: () => OnboardingSnapshot;
  subscribe: (listener: () => void) => () => void;
  start: (mode?: 'new' | 'known') => void;
  pause: () => void;
  resume: () => void;
  continue: () => void;
  setDraft: (value: string) => void;
  submit: (text?: string) => Promise<void>;
  skip: () => void;
  reconcile: () => void;
  birthConfirmed: (receipt: BirthReceipt) => boolean;
};
export type OnboardingOptions = {
  aboutMe: AboutMePort;
  birth: BirthPort;
  known?: OnboardingKnown;
  uuid?: () => string;
  onContactPreference?: (preference: OnboardingContactPreference) => Promise<ContactPreferenceReceipt>;
  readContactPreference?: () => ContactPreferenceProjection;
};
