import { useCallback, useEffect, useRef, useState } from 'react';
import type { ToolPort, ToolRead } from './types';
import { ToolViewError } from './port';

type View<T> = ToolRead<T> | { status: 'idle' | 'loading' } | { status: 'error'; message: string };
export type ToolViewOwnership = { port: ToolPort };
type Operation = { owner: ToolViewOwnership; controller: AbortController };

export function useToolRead<T>(port: ToolPort) {
  const identity = useRef<ToolViewOwnership>({ port });
  if (identity.current.port !== port) identity.current = { port };
  const ownership = identity.current;
  const owner = useRef<ToolViewOwnership | undefined>(ownership),
    operation = useRef<Operation>();
  // Port changes hide old data in this render, before passive effect cleanup.
  owner.current = ownership;
  const [snapshot, setSnapshot] = useState<{ owner: ToolViewOwnership; view: View<T> }>({
    owner: ownership,
    view: { status: 'idle' },
  });
  useEffect(() => {
    owner.current = ownership;
    return () => {
      if (operation.current?.owner === ownership) {
        operation.current.controller.abort();
        operation.current = undefined;
      }
      port.reset();
      if (owner.current === ownership) owner.current = undefined;
    };
  }, [port, ownership]);
  const reset = useCallback(() => {
    if (owner.current !== ownership) return;
    operation.current?.controller.abort();
    operation.current = undefined;
    port.reset();
    setSnapshot({ owner: ownership, view: { status: 'idle' } });
  }, [port, ownership]);
  const run = useCallback(
    async (read: (signal: AbortSignal) => Promise<ToolRead<T>>) => {
      if (owner.current !== ownership) return;
      operation.current?.controller.abort();
      port.reset();
      const current = { owner: ownership, controller: new AbortController() };
      operation.current = current;
      setSnapshot({ owner: ownership, view: { status: 'loading' } });
      const currentOperation = () =>
        !current.controller.signal.aborted && operation.current === current && owner.current === ownership;
      try {
        const next = await read(current.controller.signal);
        if (currentOperation()) setSnapshot({ owner: ownership, view: next });
      } catch (error) {
        if (currentOperation())
          setSnapshot({
            owner: ownership,
            view: {
              status: 'error',
              message: error instanceof ToolViewError ? error.message : '这次样例没有载入，条件仍保留，请重试。',
            },
          });
      }
    },
    [port, ownership],
  );
  return { view: snapshot.owner === ownership ? snapshot.view : { status: 'idle' as const }, reset, run, ownership };
}
