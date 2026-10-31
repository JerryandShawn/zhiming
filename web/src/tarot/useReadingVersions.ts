import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { operationNamespace, useAuth } from '../api/client';
import { loadReadings } from './readings';
import type { Reading } from './public';

export type VersionsState = 'loading' | 'error' | 'ready';
type Owner = { drawId: string; namespace: string; available: boolean; activation: number };
type Snapshot = { owner: Owner; status: VersionsState; values: Reading[] };

/** Read-only ownership for the selected fixed draw. Does not start or retry a run. */
export function useReadingVersions(drawId: string | undefined, activation = 0) {
  // Boolean availability alone does not change on a token A -> token B switch.
  const token = useAuth((state) => state.token);
  const loginRequired = useAuth((state) => state.loginRequired);
  const namespace = operationNamespace();
  const id = drawId ?? '';
  // Every selection activation owns a distinct snapshot, including A -> new -> A.
  const owner = useMemo<Owner>(
    () => ({ drawId: id, namespace, available: Boolean(token) && !loginRequired, activation }),
    [id, namespace, token, loginRequired, activation],
  );
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const generation = useRef(0);
  const active = useRef<Owner>();
  const invalidate = useCallback(() => {
    generation.current++;
  }, []);
  useLayoutEffect(() => {
    active.current = owner;
    return () => {
      active.current = undefined;
      invalidate();
    };
  }, [owner, invalidate]);

  const acceptVersions = useCallback(
    (values: Reading[]) => {
      if (!owner.drawId || !owner.available || active.current !== owner || owner.namespace !== operationNamespace())
        return;
      // A newer manual read/generation receipt supersedes the automatic first read.
      generation.current++;
      setSnapshot({ owner, status: 'ready', values });
    },
    [owner],
  );

  useEffect(() => {
    if (!owner.drawId || !owner.available) return;
    const version = ++generation.current;
    const owns = () =>
      version === generation.current && active.current === owner && owner.namespace === operationNamespace();
    setSnapshot((old) => ({
      owner,
      status: 'loading',
      values: old?.owner === owner ? old.values : [],
    }));
    void loadReadings(owner.drawId).then(
      (values) => {
        if (owns()) setSnapshot({ owner, status: 'ready', values });
      },
      () => {
        if (owns())
          setSnapshot((old) => ({
            owner,
            status: 'error',
            values: old?.owner === owner ? old.values : [],
          }));
      },
    );
    return invalidate;
  }, [owner, invalidate]);

  const matches = snapshot?.owner === owner && owner.available;
  return {
    versions: matches ? snapshot.values : [],
    versionsState: matches ? snapshot.status : ('loading' as VersionsState),
    acceptVersions,
  };
}
