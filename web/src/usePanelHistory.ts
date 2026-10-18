import { useCallback, useEffect, useRef, useState } from 'react';

const markerKey = '__mingjing_panel';
type Entry = { id: string; url: string };
function marker() {
  const state: unknown = history.state;
  return state && typeof state === 'object' && markerKey in state
    ? (state as Record<string, unknown>)[markerKey]
    : undefined;
}
export function usePanelHistory() {
  const [open, setOpen] = useState(false);
  const current = useRef<Entry>();
  const retiring = useRef<Entry>();
  const queuedOpen = useRef(false);
  const show = useCallback(() => {
    if (current.current) return;
    if (retiring.current) {
      queuedOpen.current = true;
      return;
    }
    const entry = { id: crypto.randomUUID(), url: location.href };
    try {
      const existing: unknown = history.state;
      history.pushState(
        { ...(existing && typeof existing === 'object' ? existing : {}), [markerKey]: entry.id },
        '',
        entry.url,
      );
      current.current = entry;
    } catch {
      // The dialog remains usable when the browser does not permit history entries.
    }
    setOpen(true);
  }, []);
  const change = useCallback(
    (next: boolean) => {
      if (next) {
        show();
        return;
      }
      queuedOpen.current = false;
      setOpen(false);
      const entry = current.current;
      current.current = undefined;
      if (entry && entry.url === location.href && marker() === entry.id) {
        retiring.current = entry;
        history.back();
      }
    },
    [show],
  );
  useEffect(() => {
    const pop = () => {
      const retired = retiring.current;
      if (retired) {
        retiring.current = undefined;
        const reopen = queuedOpen.current && location.href === retired.url;
        queuedOpen.current = false;
        if (reopen) show();
      }
      const entry = current.current;
      if (entry && (entry.url !== location.href || marker() !== entry.id)) {
        current.current = undefined;
        setOpen(false);
      }
      // Old forward entries are inert: Forward never reopens a dismissed dialog.
    };
    const route = () => {
      if (current.current?.url === location.href) return;
      current.current = undefined;
      retiring.current = undefined;
      queuedOpen.current = false;
      setOpen(false);
    };
    window.addEventListener('popstate', pop);
    window.addEventListener('hashchange', route);
    return () => {
      window.removeEventListener('popstate', pop);
      window.removeEventListener('hashchange', route);
      current.current = undefined;
      retiring.current = undefined;
      queuedOpen.current = false;
    };
  }, [show]);
  return { open, onOpenChange: change };
}
