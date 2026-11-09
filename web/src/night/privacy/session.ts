import { createPrivatePort, privateEvent, type PrivatePort } from './port';

export const privacyIdleMs = 24 * 60 * 60 * 1000;
export type PrivateMessage = { id: string; role: 'user' | 'assistant'; text: string; images: string[] };
export type PrivateSession = {
  id: string;
  generation: number;
  draft: string;
  images: string[];
  messages: PrivateMessage[];
  busy: boolean;
  lastActivity: number;
  status: string;
};
export type PrivacySnapshot = { session: PrivateSession | null; endedBy?: 'exit' | 'idle' };
export type PrivacyLease = Pick<PrivateSession, 'id' | 'generation'>;
export type PrivacyOptions = { now?: () => number; uuid?: () => string; port?: PrivatePort; idleMs?: number };

export function createPrivacySession(options: PrivacyOptions = {}) {
  const now = options.now ?? Date.now;
  const uuid = options.uuid ?? (() => crypto.randomUUID());
  const port = options.port ?? createPrivatePort();
  const idleMs = options.idleMs ?? privacyIdleMs;
  const listeners = new Set<() => void>();
  let snapshot: PrivacySnapshot = { session: null };
  let generation = 0;
  let operation = 0;
  let abort: AbortController | undefined;
  const publish = (next: PrivacySnapshot) => {
    snapshot = next;
    listeners.forEach((listener) => listener());
  };
  const end = (endedBy: 'exit' | 'idle') => {
    ++generation;
    ++operation;
    abort?.abort();
    abort = undefined;
    publish({ session: null, endedBy });
  };
  const expire = () => {
    if (snapshot.session && now() - snapshot.session.lastActivity >= idleMs) end('idle');
  };
  const current = (lease: PrivacyLease) => {
    expire();
    const session = snapshot.session;
    return session?.id === lease.id && session.generation === lease.generation ? session : undefined;
  };
  const update = (lease: PrivacyLease, patch: Partial<PrivateSession>, activity = true) => {
    const session = current(lease);
    if (session) publish({ session: { ...session, ...patch, lastActivity: activity ? now() : session.lastActivity } });
  };
  function enter() {
    expire();
    if (snapshot.session) return;
    publish({
      session: {
        id: `incognito:${uuid()}`,
        generation: ++generation,
        draft: '',
        images: [],
        messages: [],
        busy: false,
        lastActivity: now(),
        status: '',
      },
    });
  }
  async function send(lease: PrivacyLease) {
    const session = current(lease);
    if (!session || session.busy || !session.draft.trim()) return;
    const text = session.draft.trim();
    if (/^(?:结束|退出)无痕[。.!！]?$/.test(text)) {
      end('exit');
      return;
    }
    const images = [...session.images];
    const answerId = uuid();
    const messages: PrivateMessage[] = [
      ...session.messages,
      { id: uuid(), role: 'user', text, images },
      { id: answerId, role: 'assistant', text: '', images: [] },
    ];
    update(lease, { draft: '', images: [], messages, busy: true, status: '' });
    const controller = new AbortController();
    abort = controller;
    const run = ++operation;
    const valid = () => !controller.signal.aborted && run === operation && Boolean(current(lease));
    try {
      await port.respond(
        { threadId: session.id, text, images },
        (raw) => {
          if (!valid()) return;
          const event = privateEvent(raw),
            latest = current(lease);
          if (!event || !latest) return;
          update(
            lease,
            {
              messages: latest.messages.map((message) =>
                message.id !== answerId
                  ? message
                  : {
                      ...message,
                      text: event.type === 'text_delta' ? message.text + event.text : event.text,
                    },
              ),
            },
            false,
          );
        },
        controller.signal,
      );
    } catch {
      if (valid()) update(lease, { status: '这次本地演示暂时停下了，内容仍只在本页。' }, false);
    } finally {
      if (valid()) update(lease, { busy: false }, false);
      if (abort === controller) abort = undefined;
    }
  }
  return {
    idleMs,
    now,
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    enter,
    exit: () => end('exit'),
    setActive: (active: boolean) => (active ? enter() : end('exit')),
    expire,
    setDraft: (lease: PrivacyLease, draft: string) => update(lease, { draft }),
    setImages: (lease: PrivacyLease, images: string[]) => update(lease, { images: [...images] }),
    send,
    stop: (lease: PrivacyLease) => {
      if (!current(lease)) return;
      ++operation;
      abort?.abort();
      abort = undefined;
      update(lease, { busy: false, status: '已停止这一轮，内容仍只在本页。' });
    },
  };
}
