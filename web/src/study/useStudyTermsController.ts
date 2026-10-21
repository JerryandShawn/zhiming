import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { usePanelHistory } from '../usePanelHistory';
import type { StudyPort, StudyScope, StudySystem, TermDetail, TermSummary } from './types';

type Owner = { port: StudyPort | undefined };
export type TermView =
  | { phase: 'loading' }
  | { phase: 'choose'; candidates: TermSummary[] }
  | { phase: 'ready'; detail: TermDetail }
  | { phase: 'unavailable'; message: string };
type Action = { kind: 'id'; id: string } | { kind: 'label'; label: string; system?: StudySystem };
type Attempt = { id: number; scope: StudyScope; controller: AbortController };
const emptyTerms: readonly TermSummary[] = [];

export function useStudyTermsController(port: StudyPort | undefined) {
  const owner = useMemo<Owner>(() => ({ port }), [port]);
  const { open: panelOpen, onOpenChange } = usePanelHistory();
  const [index, setIndex] = useState<{ owner: Owner; terms: TermSummary[]; failed: boolean }>();
  const [state, setState] = useState<{ owner: Owner; value: TermView }>();
  const activeOwner = useRef<Owner>();
  const serial = useRef(0),
    attempt = useRef<Attempt>();
  const returnTo = useRef<HTMLElement>(),
    wantsOpen = useRef(false);
  const wasOpen = useRef(false),
    openedRead = useRef<number>();
  const cancelRead = useCallback(() => {
    serial.current++;
    const previous = attempt.current;
    attempt.current = undefined;
    previous?.controller.abort();
    previous?.scope.dispose();
  }, []);

  useLayoutEffect(() => {
    activeOwner.current = owner;
    wantsOpen.current = false;
    setState(undefined);
    onOpenChange(false);
    return () => {
      activeOwner.current = undefined;
      wantsOpen.current = false;
      cancelRead();
    };
  }, [owner, cancelRead, onOpenChange]);

  useEffect(() => {
    if (!owner.port) return;
    let current = true,
      scope: StudyScope | undefined;
    const controller = new AbortController();
    try {
      scope = owner.port.createScope();
      void scope.search({ text: '' }, controller.signal).then(
        (result) => {
          if (current && !controller.signal.aborted && activeOwner.current === owner)
            setIndex({
              owner,
              terms: result.status === 'ready' ? result.value : [],
              failed: result.status !== 'ready',
            });
        },
        () => {
          if (current && !controller.signal.aborted && activeOwner.current === owner)
            setIndex({ owner, terms: [], failed: true });
        },
      );
    } catch {
      if (current && activeOwner.current === owner) setIndex({ owner, terms: [], failed: true });
    }
    return () => {
      current = false;
      controller.abort();
      scope?.dispose();
    };
  }, [owner]);

  // Back can close the history owner directly. A newly queued opening has a
  // newer serial and must not be discarded by the retiring entry's transition.
  useLayoutEffect(() => {
    if (panelOpen) openedRead.current = serial.current;
    else if (wasOpen.current && openedRead.current === serial.current) {
      wantsOpen.current = false;
      cancelRead();
      setState(undefined);
    }
    wasOpen.current = panelOpen;
  }, [panelOpen, cancelRead]);

  const run = useCallback(
    (action: Action, origin?: HTMLElement) => {
      if (!owner.port || activeOwner.current !== owner) return;
      cancelRead();
      const id = ++serial.current;
      const controller = new AbortController();
      if (origin) returnTo.current = origin;
      wantsOpen.current = true;
      if (panelOpen) openedRead.current = id;
      onOpenChange(true);
      setState({ owner, value: { phase: 'loading' } });
      const current = () => activeOwner.current === owner && serial.current === id && !controller.signal.aborted;
      void (async () => {
        try {
          const scope = owner.port!.createScope();
          attempt.current = { id, scope, controller };
          let termId: string;
          if (action.kind === 'label') {
            const resolved = await scope.resolveTerm(action.label, action.system, controller.signal);
            if (!current()) return;
            if (resolved.status === 'unavailable') {
              setState({ owner, value: { phase: 'unavailable', message: resolved.message } });
              return;
            }
            if (resolved.status === 'ambiguous') {
              setState({ owner, value: { phase: 'choose', candidates: resolved.candidates } });
              return;
            }
            termId = resolved.term.term_id;
          } else termId = action.id;
          const detail = await scope.readTerm(termId, controller.signal);
          if (!current()) return;
          setState({
            owner,
            value:
              detail.status === 'ready'
                ? { phase: 'ready', detail: detail.value }
                : { phase: 'unavailable', message: detail.message },
          });
        } catch {
          if (current())
            setState({ owner, value: { phase: 'unavailable', message: '术语资料暂时没有展开，请关闭后重新选择。' } });
        }
      })();
    },
    [owner, cancelRead, panelOpen, onOpenChange],
  );

  const close = useCallback(() => {
    wantsOpen.current = false;
    cancelRead();
    // This close already retired its read. A queued reopen belongs to the next
    // history entry, even before the old entry's asynchronous Back arrives.
    wasOpen.current = false;
    openedRead.current = undefined;
    setState(undefined);
    onOpenChange(false);
  }, [cancelRead, onOpenChange]);
  const returnFocus = useCallback(() => {
    if (wantsOpen.current) return;
    const origin = returnTo.current;
    const target = origin?.isConnected ? origin : document.getElementById('main');
    target?.focus({ preventScroll: true });
  }, []);
  const view = state?.owner === owner ? state.value : undefined;
  const terms = index?.owner === owner && !index.failed ? index.terms : emptyTerms;
  return {
    terms,
    indexStatus:
      !port || (index?.owner === owner && index.failed) ? 'unavailable' : index?.owner === owner ? 'ready' : 'loading',
    view,
    open: panelOpen && view !== undefined,
    openTerm: (id: string, origin: HTMLElement) => run({ kind: 'id', id }, origin),
    openLabel: (label: string, origin: HTMLElement, system?: StudySystem) =>
      run({ kind: 'label', label, system }, origin),
    choose: (id: string) => run({ kind: 'id', id }),
    close,
    returnFocus,
  };
}
