import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createStudyLoadSession, type StudyLoadSession } from './staticLoader';
import type { StudyMetadata, StudyPort } from './types';

type Factory = () => StudyLoadSession;
type Owner = { createSession: Factory };
type Activation = { owner: Owner; session: StudyLoadSession; request?: object; controller?: AbortController };
type View = { status: 'loading' | 'error' } | { status: 'ready'; port: StudyPort; metadata: StudyMetadata };
type Snapshot = { owner: Owner; activation: Activation; request: object; view: View };

/** Each effect activation owns a new session, including StrictMode replay. */
export function useStudyCatalog(createSession: Factory = createStudyLoadSession) {
  const owner = useMemo<Owner>(() => ({ createSession }), [createSession]);
  const active = useRef<Activation>();
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const start = useCallback((activation: Activation) => {
    if (active.current !== activation) return;
    activation.controller?.abort();
    const controller = new AbortController(),
      request = {};
    activation.request = request;
    activation.controller = controller;
    const current = () => active.current === activation && activation.request === request && !controller.signal.aborted;
    setSnapshot({ owner: activation.owner, activation, request, view: { status: 'loading' } });
    void activation.session.reload(controller.signal).then(
      (port) => {
        if (!current()) {
          port.dispose();
          return;
        }
        try {
          const metadata = port.metadata();
          setSnapshot({ owner: activation.owner, activation, request, view: { status: 'ready', port, metadata } });
        } catch {
          port.dispose();
          if (current()) setSnapshot({ owner: activation.owner, activation, request, view: { status: 'error' } });
        }
      },
      () => {
        if (current()) setSnapshot({ owner: activation.owner, activation, request, view: { status: 'error' } });
      },
    );
  }, []);
  useEffect(() => {
    const activation: Activation = { owner, session: owner.createSession() };
    active.current = activation;
    start(activation);
    return () => {
      activation.controller?.abort();
      activation.session.dispose();
      if (active.current === activation) active.current = undefined;
    };
  }, [owner, start]);
  const reload = useCallback(() => {
    const activation = active.current;
    if (activation?.owner === owner) start(activation);
  }, [owner, start]);
  const current =
    snapshot?.owner === owner && snapshot.activation === active.current && snapshot.request === active.current?.request;
  return { view: current ? snapshot.view : ({ status: 'loading' } as const), reload };
}
