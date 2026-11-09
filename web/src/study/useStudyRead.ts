import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { StudyEvidenceRef, StudyPort, StudyRead, StudyScope } from './types';

type Owner = { port?: StudyPort; key: string };
type Activation = { owner: Owner; scope: StudyScope; request?: object; controller?: AbortController };
type View<T> = StudyRead<T> | { status: 'idle' | 'loading' | 'error' };
type Snapshot<T> = { owner: Owner; activation: Activation; request?: object; view: View<T> };

/** Query and port identity hide old results in the first render, before cleanup. */
export function useStudyRead<T>(port: StudyPort | undefined, key: string) {
  const owner = useMemo<Owner>(() => ({ port, key }), [port, key]);
  const active = useRef<Activation>();
  const [snapshot, setSnapshot] = useState<Snapshot<T>>();
  useLayoutEffect(() => {
    if (!owner.port) return;
    const activation: Activation = { owner, scope: owner.port.createScope() };
    active.current = activation;
    return () => {
      activation.controller?.abort();
      activation.scope.dispose();
      if (active.current === activation) active.current = undefined;
    };
  }, [owner]);
  const run = useCallback(
    async (read: (scope: StudyScope, signal: AbortSignal) => Promise<StudyRead<T>>) => {
      const activation = active.current;
      if (!activation || activation.owner !== owner) return;
      activation.controller?.abort();
      activation.scope.reset();
      const controller = new AbortController(),
        request = {};
      activation.controller = controller;
      activation.request = request;
      const current = () =>
        active.current === activation && activation.request === request && !controller.signal.aborted;
      setSnapshot({ owner, activation, request, view: { status: 'loading' } });
      try {
        const view = await read(activation.scope, controller.signal);
        if (current()) setSnapshot({ owner, activation, request, view });
      } catch {
        if (current()) {
          activation.scope.reset();
          setSnapshot({ owner, activation, request, view: { status: 'error' } });
        }
      }
    },
    [owner],
  );
  const resolveEvidence = useCallback(
    (reference: StudyEvidenceRef) => {
      const activation = active.current;
      if (
        snapshot?.owner !== owner ||
        snapshot.activation !== activation ||
        snapshot.request !== activation?.request ||
        snapshot.view.status !== 'ready'
      )
        return;
      return activation?.scope.resolveEvidence(reference);
    },
    [owner, snapshot],
  );
  const current =
    snapshot?.owner === owner && snapshot.activation === active.current && snapshot.request === active.current?.request;
  return { view: current ? snapshot.view : ({ status: 'idle' } as const), run, resolveEvidence, owner };
}
